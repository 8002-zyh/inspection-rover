#!/usr/bin/env python3
#coding=UTF-8
# ------------------------------------------------------------------ #
# @file    : ROSPY_Orin_basecontrol_202406v1.py
# @platform: Python & ROS
# @board   : Jetson Xavier NX
# @brief   : 适用4代滑板底盘
#            将ROS订阅到的底盘控制量（电机、舵机）进行处理并通过串口通信进行控制
# 
# @author  : GFN hq
# @date    : 2024/6
# @web     : http ://www.relaxingtechnology.com/
# @e-mail  : relaxingtech@qq.com
# Copyright (C) 2023 Relaxing Technology Chongqing Co.,Ltd. All rights reserved.
# ------------------------------------------------------------------ #
import serial
import rospy
from std_msgs.msg import Int32, Float64
import math
import time
MMWR_PORT = "/dev/ttyTHS0"
MMWR_BAUD_RATE = 115200
scs_mode_ackerman = b'\x00'
scs_mode_4matic_diff = b'\x01'
scs_mode_4matic_same = b'\x02'
motor_data_pandn = b'\x00'
SCS_mode = ''
Headlight_off = b'\x00'
Headlight_on = b'\x01'
SCS_MODE_ACKERMAN = 0
SCS_MODE_4MATIC_DIFF = 1
SCS_MODE_4MATIC_SAME = 2
scs_mode = None


# 传动比
TRANS_RATIO = 6.287
# 轮胎半径
WHEEL_RADIUS = 0.033 
# 占空比安全限幅(浮点型)
MIN_DUTY =0.0
MAX_DUTY =1.4
# 电机转速安全限幅（整型）
MIN_RPM =900
MAX_RPM = 3000
class Motor:
    def __init__(self):
        self.motor = 0.0
        self.last_update_time = time.time()
        self.timeout = 2  # 超时时间（秒）

    @staticmethod
    def _vel2duty(vel):
        rpm = vel * 60 * TRANS_RATIO / (2 * 3.14 * WHEEL_RADIUS)
        duty = (abs(rpm) - 100) * 0.11 / 1200 + 0.01 if rpm > 0 else -((abs(rpm) - 100) * 0.11 / 1200 + 0.01)
        return duty
    
    # duty
    def writeDuty_sub(self, duty_sub: Float64):
        if isinstance(duty_sub, Float64):
            self.motor = duty_sub.data
            self.last_update_time = time.time()


    # rpm    
    def writeRPM_sub(self, rpm_sub: Int32):
        if isinstance(rpm_sub, Int32):
            self.motor = rpm_sub.data
            self.last_update_time = time.time()

    # velocity
    def writeVelocity_sub(self, velocity_sub: Float64):
        if isinstance(velocity_sub, Float64):
            self.motor = Motor._vel2duty(velocity_sub.data)
            self.last_update_time = time.time()
    def check_timeout(self):
        if time.time() - self.last_update_time > self.timeout:
            self.motor = 0.0
# 舵机最小转向角度，角度制->弧度制
MIN_DELTA: float = math.radians(-20) 
# 舵机最大转向角度，角度制->弧度制
MAX_DELTA: float = math.radians(20) 
# detla转position的系数
COEFFICIENT: int = 1
# 舵机中间角度位置
CENTER_POSITION: int = 1500
# 舵机最小角度位置
MIN_POSITION: int = 800 
#舵机最大角度位置
MAX_POSITION: int = 2200 
class Servo:
    def __init__(self):
        self.servo : int = 1500
        self._h_positionRange: float = (MAX_POSITION - MIN_POSITION) / 2
        self._h_deltaRange: float = (MAX_DELTA - MIN_DELTA) / 2     # 弧度制

    # 订阅position
    def position_write_sub(self, position: Int32):
        if isinstance(position, Int32):
            self.servo = position.data

     # 订阅delta
    def delta_write_sub(self, delta: Float64):
        delta.data = delta.data if delta.data > MIN_DELTA else delta.data
        delta.data = delta.data if delta.data < MAX_DELTA else delta.data
        self.servo = int(COEFFICIENT * ((delta.data - 0) / self._h_deltaRange 
                                                 * self._h_positionRange) + CENTER_POSITION)



# 串口创建函数
def openMMWPort(port=MMWR_PORT, baudRate=MMWR_BAUD_RATE):
    try:
        uart = serial.Serial(port, baudRate, timeout=5)
        # time.sleep(0.5)
    except Exception as error:
        print("Failed to open serial port\n", error)
        exit(0)
    else:
        return uart #返回串口类对象


def send_data_import(uart: serial.Serial,motor_value,scs_steering,scs_mode,Headlight):
    protocol_header = b'\xFF' #协议头
    protocol_ender = b'\xFE'  #协议尾
    if motor_value<0:
        motor_value = -motor_value
        motor_data_pandn = b'\x01'       #电机数据正负符号位（00为正数，01为负数）
    else:
        motor_data_pandn = b'\x00'
        
    motor_input = motor_data_deal(motor_value)
    steering_input = scs_data_deal(scs_steering)

    data_packet = protocol_header  + motor_data_pandn + motor_input + steering_input + scs_mode + Headlight + protocol_ender
    # print(data_packet) 

    try:
        uart.write(data_packet) #发送数据包
    except Exception as exception_error:
        print("Error occurred. Exiting Program")
        print("Error: " + str(exception_error)) 


def receive_data(uart: serial.Serial):
    data_length = 14 #包含数据帧头、电机转速低八位、转速高八位、舵机低八位、舵机高八位、转向模式、转向灯信息（00表示关闭，01表示右转，02表示左转）、大灯信息（00关闭、01开启）、尾灯信息（00关闭，01开启）、轮速正负（1为负）数据帧尾的总字节长度
    state_num = 0
    global SCS_mode,headlight,taillight
    while(True):                                                                                                             
    
        try:
            #使用状态机进行中断接收数据
            if state_num == 0:
                if uart.is_open and uart.in_waiting > 0:  # 未检测到数据时串口没有字节缓存
                    data_buffer = []        #初始化缓存区，并在循环过程中清除缓存
                    # if state_num == 0:
                    Read_buffer = uart.read()   #首先读取一个字节
                    # print(Read_buffer)
                    # break
                    if Read_buffer == b'\xff':    #判断数据帧头
                            state_num = 1
                            data_buffer = uart.read(data_length-1)  #读取数据内容，接收除数据帧头以外的剩余字节
                            if data_buffer[data_length-2]== 254:      #判断数据帧尾
                                Rpm = data_buffer[0]*256+data_buffer[1]
                                # if Rpm >32768:
                                #     Rpm=Rpm-65536
                                SCS = data_buffer[2]*256+data_buffer[3]
                                if data_buffer[11] == 1:
                                    vesc_rpm = -(data_buffer[9]*256+data_buffer[10])
                                elif data_buffer[11] ==0:
                                    vesc_rpm = data_buffer[9]*256+data_buffer[10]
                                if data_buffer[4]==0:
                                    SCS_mode = '阿克曼转向' 
                                elif data_buffer[4]==1:
                                    SCS_mode = '四轮异向'
                                elif data_buffer[4]==2:
                                    SCS_mode = '四轮同向'

                                if data_buffer[5]==0:
                                    turn_light_inf = '转向灯关闭'
                                elif data_buffer[5]==1:
                                    turn_light_inf = '右转向灯闪烁'
                                elif data_buffer[5]==2:
                                    turn_light_inf = '左转向灯闪烁'
                                if data_buffer[6] == 0:
                                    headlight = '车大灯关闭'
                                elif data_buffer[6] == 1:
                                    headlight = '车大灯开启'
                                if data_buffer[7] == 0:
                                    taillight = '尾灯关闭'
                                elif data_buffer[7] == 1:
                                    taillight = '尾灯开启'
                                if data_buffer[8] == 1:
                                    Rpm = -Rpm
                                print("轮速：",Rpm,"舵机数值：",SCS,SCS_mode,turn_light_inf,headlight,taillight,"vesc_Rpm:",vesc_rpm,"r/min")
                                pub_code_rpm.publish(Rpm)
                                break    #读取到一帧数据后跳出循环
                            else:                   
                                state_num = 0    #读取数据出错重新读取
                    else:
                        state_num = 0        #未读取到数据帧头重新读取
        except KeyboardInterrupt:
            uart.close()
            exit(0)

# 电机限幅及数据转码
def motor_data_deal(motor_value):
    if isinstance(motor_value, float): #占空比限幅[MIN_DUTY , MAX_DUTY]
        motor_value = motor_value if motor_value>=MIN_DUTY else MIN_DUTY
        motor_value = motor_value if motor_value<=MAX_DUTY else MAX_DUTY
        motor_value = int(motor_value*100)
        motor_input = motor_value.to_bytes(2,byteorder='little')
    elif isinstance(motor_value, int): #转速限幅[MIN_RPM , MAX_RPM]
        motor_value = motor_value if motor_value>=MIN_RPM else MIN_RPM
        motor_value = motor_value if motor_value<=MAX_RPM else MAX_RPM
        motor_input = motor_value.to_bytes(2,byteorder='little')
    else:
        print("电机值数据类型有误！！！请确保电机值为占空比[<1.4](浮点型)或转速[900rpm-3500rpm](整型)")
        exit(0)
    # print("222   ",motor_value )
    return motor_input

# 舵机限幅保护及数据转码
def scs_data_deal(scs_steering):
    if isinstance(scs_steering, int):
         # 舵机限幅处理
        steering_input = scs_steering if scs_steering> MIN_POSITION else MIN_POSITION
        steering_input = scs_steering if scs_steering< MAX_POSITION else MAX_POSITION
        steering_input = scs_steering.to_bytes(2,byteorder='little')
    else:
        print("舵机值数据类型有误！！！请确保舵机值为[800,2200](整型)")
        exit(0)
    #print("222   ",scs_steering)
    return steering_input
def scs_mode_callback(data):
    global scs_mode,qewe
    scs_mode = data.data

    
if __name__ == "__main__":
    Uart = openMMWPort(port=MMWR_PORT, baudRate=MMWR_BAUD_RATE)  # 打开串口
    rospy.init_node("chasis_control_node")
    motorObj = Motor()
    servoObj = Servo()
    #发布编码器转速
    pub_code_rpm = rospy.Publisher("/motor_code_rpm",Int32,queue_size=10)
    # 订阅电机
    rospy.Subscriber("/motor_write_duty", Float64, motorObj.writeDuty_sub, queue_size=10)
    rospy.Subscriber("/motor_write_rpm", Int32, motorObj.writeRPM_sub, queue_size=10)
    rospy.Subscriber("/motor_write_velocity", Float64, motorObj.writeVelocity_sub, queue_size=10)
    rospy.Subscriber("/scs_mode", Int32, scs_mode_callback, queue_size=10)

    #订阅舵机
    rospy.Subscriber("/servo_write_position", Int32, servoObj.position_write_sub, queue_size=10)
    rospy.Subscriber("/servo_write_delta", Float64, servoObj.delta_write_sub, queue_size=10)
    
    #频率低于400会导致电机舵机运行状态不正常
    rate = rospy.Rate(500)
    while not rospy.is_shutdown():
        scs_mode = 0
        if scs_mode is not None:
            # 根据 scs_mode 的值选择对应的字节
            if scs_mode == SCS_MODE_ACKERMAN:
                scs_mode_byte = b'\x00'
            elif scs_mode == SCS_MODE_4MATIC_DIFF:
                scs_mode_byte = b'\x01'
            elif scs_mode == SCS_MODE_4MATIC_SAME:
                scs_mode_byte = b'\x02'
            else:
                rospy.logwarn("Unknown scs_mode value: %d", scs_mode)
                scs_mode_byte = b'\x00'  # 默认值

        # print(motorObj.motor)
        # print(servoObj.servo)
            send_data_import(Uart, motorObj.motor, servoObj.servo, scs_mode=scs_mode_byte, Headlight=Headlight_off)
        receive_data(Uart)
        motorObj.check_timeout()
        rate.sleep()
