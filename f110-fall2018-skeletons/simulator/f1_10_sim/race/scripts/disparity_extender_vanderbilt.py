#!/usr/bin/env python
from sensor_msgs.msg import LaserScan
import time
import rospy
import copy
import numpy as np
from race.msg import drive_param
import math

""" 
The goal of this script is to implement the disparity extender used by UNC on our own car from previous tests just using their code out of the box, we were not so lucky
Credit to their team this code is largely inspired by the post (https://www.nathanotterness.com/2019/04/the-disparity-extender-algorithm-and.html)
"""

class DisparityExtenderDriving(object):


    #constructor for our DisparityExtenderDrivng Object
    #stores configuration parameters neccessary for successful execution of our algorithm
    def __init__(self):

        # This is actually "half" of the car width, plus some tolerance.
        # Controls the amount disparities are extended by.

        self.car_width = 0.25#0.50

        # This is the difference between two successive LIDAR scan points that
        # can be considered a "disparity". (As a note, at 7m there should be
        # ~0.04m between scan points.)

        self.disparity_threshold = 0.3

        # This is the arc width of the full LIDAR scan data, in degrees, We are using the Hokuyo UST-10LX

        self.scan_width = 270.0

        # The maximum range for our LIDAR is 10m

        self.lidar_max_range=10.0

        # This is the radius to the left or right of the car that must be clear
        # when the car is attempting to turn left or right.

        self.turn_clearance = 0.30

        # This is the maximum steering angle of the car, in degrees.

        self.max_turn_angle = 34.0

        # The slowest speed the car will go
        # Good value here is 0.1

        self.min_speed = 1.0

        # The maximum speed the car will go (the absolute max for the motor is
        # 0.5, which is *very* fast). 0.15 is a good max for slow testing.

        self.max_speed = 1.15 #.20

        self.absolute_max_speed = 1.20 # 0.3

        # The forward distance at which the car will go its minimum speed.
        # If there's not enough clearance in front of the car it will stop.

        self.min_distance = 0.15

        # The forward distance over which the car will go its maximum speed.
        # Any distance between this and the minimum scales the speed linearly.

        self.max_distance = 3.0

        # The forward distance over which the car will go its *absolute
        # maximum* speed. This distance indicates there are no obstacles in
        # the near path of the car. Distance between this and the max_distance
        # scales the speed linearly.

        self.no_obstacles_distance = 6.0


        #publisher for speed and angles 

        self.pub_drive_param = rospy.Publisher('drive_parameters',drive_param, queue_size=5)

        #this functionality depends on a functioning LIDAR so it subscribes to the lidar scans
        rospy.Subscriber('scan', LaserScan, self.lidar_callback)

        #create a variable that will store the lidar distances
        self.lidar_distances=None

        #store the value of 0.25 degrees in radians
        self.angle_step=(0.25)*(math.pi/180)

    

    """This function computes which direction we should be targeting"""
    def calculate_target_distance(self,arr):
        if(len(arr)==1):
            return arr[0]
        else:
            mid=int(len(arr)/2)
            return arr[mid]

    """ Main function callback for the car"""
    def lidar_callback(self,data):
        ranges=data.ranges
        #convert the range to a numpy array so that we can process the data
        limited_ranges=np.asarray(ranges)
        #ignore everything outside the -90 to 90 degree range
        limited_ranges[0:180]=0.0
        limited_ranges[901:]=0.0
        #add this so that the last element is not detected as a disparity
        limited_ranges[901]=limited_ranges[900]
        indices=np.where(limited_ranges>=10.0)[0]
        limited_ranges[indices]=(data.range_max)-0.1

        #calculate the disparities between samples
        threshold=self.disparity_threshold
        car_width=self.car_width
        disparities=self.find_disparities(limited_ranges,threshold)
        
        #go through the disparities and extend the disparities 
        new_ranges=self.extend_disparities(limited_ranges,disparities,car_width)

        #compute the max_value of the new limited values
        max_value=max(new_ranges)
        target_distances=np.where(new_ranges>=max_value)[0]
        
        driving_distance=self.calculate_target_distance(target_distances)
        print(driving_distance,max_value,new_ranges[driving_distance])

    """ Scans each pair of subsequent values, and returns an array of indices
        where the difference between the two values is larger than the given
        threshold. The returned array contains only the index of the first value
        in pairs beyond the threshold. 
        
        returns list of indices where disparities exist
        """

    def find_disparities(self,arr,threshold):
        to_return = []
        values = arr
        #print("Why would you consider disparities behind the car",len(values))
        for i in range(180,901):
            if abs(values[i] - values[i + 1]) >= threshold:
                #print("disparity: ",(values[i], values[i + 1]))
                #print("indices: ",(i, i + 1))
                to_return.append(i)
        return to_return

    """ Returns the number of points in the LIDAR scan that will cover half of
        the width of the car along an arc at the given distance. """
    def calculate_samples_based_on_arc_length(self,distance,car_width):
        
        # This isn't exact, because it's really calculated based on the arc length
        # when it should be calculated based on the straight-line distance.
        # However, for simplicty we can just compensate for it by inflating the
        # "car width" slightly.

         #store the value of 0.25 degrees in radians
        angle_step=(0.25)*(math.pi/180)
        arc_length=angle_step*distance
        return int(math.ceil(car_width / arc_length))

    """Extend the disparities and don't go outside the specified region"""
    def extend_disparities(self,arr,disparity_indices,car_width):
        ranges=np.copy(arr)
        for i in disparity_indices:
            #get the values corresponding to the disparities
            value1=ranges[i]
            value2=ranges[i+1]
            #Depending on which value is greater we either need to extend left or extend right
            if(value1<value2):
                nearer_value=value1
                nearer_index=i
                extend_positive=True
            else:
                nearer_value=value2
                extend_positive=False
                nearer_index=i+1
            #compute the number of samples needed to "extend the disparity"
            samples_to_extend=self.calculate_samples_based_on_arc_length(nearer_value,car_width)
            #print("Samples to Extend:",samples_to_extend)

            #loop through the array replacing indices that are larger and making sure not to go out of the specified regions   
            current_index = nearer_index
            for i in range(samples_to_extend):
                    # Stop trying to "extend" the disparity point if we reach the
                    # end of the array.
                    if current_index < 180:
                        current_index = 180
                        break
                    if current_index >=901:
                        current_index =900
                        break
                    # Don't overwrite values if we've already found a nearer point
                    if ranges[current_index] > nearer_value:
                        ranges[current_index] = nearer_value
                    # Finally, move left or right depending on the direction of the
                    # disparity.
                    if extend_positive:
                        current_index += 1
                    else:
                        current_index -= 1
            return ranges

if __name__ == '__main__':
    rospy.init_node('disparity_extender', anonymous=True)
    extendObj=DisparityExtenderDriving()
    rospy.Subscriber('scan', LaserScan, extendObj.lidar_callback)
    rospy.spin()