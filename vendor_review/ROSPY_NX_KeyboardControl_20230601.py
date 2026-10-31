#!/usr/bin/env python3
#coding=UTF-8
# ------------------------------------------------------------------ #
# @file    : ROSPY_NX_KeyboardControl_202306v1.py
# @platform: Python & ROS
# @board   : Jetson Xavier NX
# @brief   : 基于ROS的键盘控制
# 
# @author  : Zhonglw
# @date    : 2023/6
# @web     : http ://www.relaxingtechnology.com/
# @e-mail  : relaxingtech@qq.com
# Copyright (C) 2023 Relaxing Technology Chongqing Co.,Ltd. All rights reserved.
# ------------------------------------------------------------------ #
import pygame
import rospy
from std_msgs.msg import Float64, Int32

DEFAULT_DUTY = 0.07
SPEED_DUTY = 0.07
MAX_DUTY = 0.07
MIN_DUTY = - 0.07
MAX_POSITION = 2200
MIN_POSITION = 800

def keyType():
    global UpFlag, DownFlag, LeftFlag, RightFlag
    global Duty, Position
    
    if UpFlag and DownFlag:
        pass
    elif UpFlag and not DownFlag:
        Duty = DEFAULT_DUTY if Duty <= 0 else Duty + 0.01
    elif not UpFlag and DownFlag:
        Duty = - DEFAULT_DUTY if Duty >= 0 else Duty - 0.01
    else:
        Duty = Duty - 0.015 if Duty > 0 else Duty + 0.015
        Duty = 0.0 if abs(Duty - 0.0) <= 0.005 else Duty

    Duty = Duty if Duty < MAX_DUTY else MAX_DUTY
    Duty = Duty if Duty > MIN_DUTY else MIN_DUTY


    if LeftFlag and RightFlag:
        pass
    elif LeftFlag and not RightFlag:
        Position = 1450 if Position > 1450 else Position - 200
    elif not LeftFlag and RightFlag:
        Position = 1450 if Position < 1450 else Position + 200
    else:
        Position = Position + 100 if Position < 1450 else Position - 100
        Position = 1450 if abs(Position - 1450) <= 100 else Position

    Position = Position if Position < MAX_POSITION else MAX_POSITION
    Position = Position if Position > MIN_POSITION else MIN_POSITION
    return Duty, Position


if __name__ == "__main__":
    print("Press and hold the button to control the car:"
          "\tw | up:\t\tforward\n"
          "\ts | down:\tbackward\n"
          "\ta | left:\tturn left\n"
          "\td | right:\tturn right\n"
          "\tspace:\tstop\n"
          "----------\n"
          "ESC: exit")

    rospy.init_node("keyboard_control")
    motor_pub = rospy.Publisher("/motor_write_duty", Float64, queue_size=10)
    servo_pub = rospy.Publisher("/servo_write_position", Int32, queue_size=10)
    rate = rospy.Rate(10)

    pygame.init()
    pygame.display.set_mode((600, 400))
    pygame.display.set_caption("RUN!!!")

    Duty = 0
    Position = 1450
    UpFlag = DownFlag = False
    LeftFlag = RightFlag = False
    SpaceFlag = ShiftFlag = False

    while True:
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                pygame.quit()
                exit(0)

            elif event.type == pygame.KEYDOWN:  # 按下按键
                if event.key == pygame.K_ESCAPE:
                    pygame.quit()
                    exit(0)
                elif event.key == pygame.K_UP:
                    UpFlag = True
                elif event.key == pygame.K_DOWN:
                    DownFlag = True
                elif event.key == pygame.K_LEFT:
                    LeftFlag = True
                elif event.key == pygame.K_RIGHT:
                    RightFlag = True
                elif event.key == pygame.K_SPACE:
                    SpaceFlag = True

            elif event.type == pygame.KEYUP:    # 松开按键
                if event.key == pygame.K_UP:
                    UpFlag = False 
                elif event.key == pygame.K_DOWN:
                    DownFlag = False
                elif event.key == pygame.K_LEFT:
                    LeftFlag = False
                elif event.key == pygame.K_RIGHT:
                    RightFlag = False
                elif event.key == pygame.K_SPACE:
                    SpaceFlag = False

        duty, position = keyType()
        if SpaceFlag == True:
            duty = 0
        servo_pub.publish(position)
        motor_pub.publish(duty)
        
        pygame.display.update()
        rate.sleep()

