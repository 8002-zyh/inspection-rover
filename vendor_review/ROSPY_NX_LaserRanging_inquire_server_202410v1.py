#!/usr/bin/env python3
#coding=UTF-8
# ------------------------------------------------------------------ #
# @file    : ROSPY_NX_LaserRanging_inpuire_server_202410v1.py
# @platform: Python & ROS
# @board   : Jetson Xavier NX
# @brief   : 激光测距传感器（TDFSense P）检测程序（查询模式），服务端
#           
#            使用查询模式时，需在上位机中将激光测距传感器设置为INQUIRE模式
#
#            使用自定义消息：
#               laser_ranging_srv.srv
#               # request
#               - int32 id_request: 客户端请求查询数据的传感器的id号，默认为0
#               # response
#               - int32 id: 激光测距传感器ID
#               - float64 distance: 检测距离，单位m
#               - int32 singal_strength: 信号强度，强度为0时表示超出检测范围
#            注：使用此代码前，需要配置CMakeLists.txt文件
#
#            import:
#               - from [功能包].srv import laser_ranging_srv, laser_ranging_srvRequest, laser_ranging_srvResponse
#
#            source:
#               - source ./[自定义消息所在的工作空间]/devel/setup.bash
#
#            API:
#               node name:  laser_inquire_node
#               topic name: laser_server
#               topic type: laser_ranging_srv
#
# @author  : Zhonglw
# @date    : 2023/5
# @web     : http ://www.relaxingtechnology.com/
# @e-mail  : relaxingtech@qq.com
# Copyright (C) 2023 Relaxing Technology Chongqing Co.,Ltd. All rights reserved.
# ------------------------------------------------------------------ #
import serial
import rospy
from laserranging_data.srv import laser_ranging_srv, laser_ranging_srvRequest, laser_ranging_srvResponse


LASER_PORT = '/dev/ttyACM0'
LASER_BAUD_RATE = 921600


def analysisData(dataList) -> int:
    result, bit = 0, 0
    for i in range(len(dataList)):
        result += dataList[i] << bit
        bit += 8
    return result


def analysisTime(dataList) -> int: return analysisData(dataList)   # ms
def analysisDistance(dataList) -> float: return analysisData(dataList) / 1000 # m
def analysisSignal(dataList) -> int:  return analysisData(dataList)
def sumCheck(dataList, sumByte) -> bool: return True if sum(dataList) & 0xFF == sumByte else False


# 解析数据
def analysis(result) -> tuple:
    resultList = list(result)
    
    if resultList[0] == int("0x57", 16) and resultList[1] == int("0x00", 16) and \
        sumCheck(resultList[: -1], resultList[-1]):   # 验证协议头和校验和
        id: int = resultList[3]     # id
        sysTime: int = analysisTime(resultList[4: 8])    # 时间，ms
        distance: float = analysisDistance(resultList[8: 11])  # 检测距离，m
        dis_status: int = resultList[11]    # 状态
        signal_strength: int = analysisSignal(resultList[12: 14])   # 信号强度
        
        return id, distance, signal_strength
    else:
        return None, None, None


def inquire(id):
    # 生成查询指令
    id_ins = hex(id)[2:] if len(hex(id)[2:]) == 2 else "0" + hex(id)[2:]
    checksum = sum([0x57, 0x10, 0xFF, 0xFF, id, 0xFF, 0xFF]) & 0xFF
    checksum_ins = hex(checksum)[2:] if len(hex(checksum)[2:]) == 2 else "0" + hex(checksum)[2:]
    instruct = "5710FFFF" + id_ins + "FFFF" + checksum_ins
    # 写入指令
    Port.write(bytes.fromhex(instruct))
    # 读取输出
    result = Port.read(16)
    # 解析数据
    id, distance, signal_strength = analysis(result)
    return id, distance, signal_strength


def callback(request: laser_ranging_srvRequest):
    # 检查数据类型，可省略
    if not isinstance(request, laser_ranging_srvRequest):
        return None, None, None
    if not isinstance(request.id_request, int):
        return None, None, None
    
    # 创建响应消息包
    response = laser_ranging_srvResponse()
    # 查询激光测距传感器的检测结果
    response.id, response.distance, response.signal_strength = inquire(request.id_request)
    
    if response.signal_strength == 0:
        # 信号强度为0时，超出检测范围，终端无数据输出，服务输出数据为随机无效值
        rospy.loginfo("Laser ranging service: Out of detection range.")
    else:
        rospy.loginfo("Laser ranging service:\nid: %d\ndistance: %f\nsignal strength: %d", 
                      response.id, response.distance, response.signal_strength)
    return response
    

if __name__ == "__main__":
    # 打开激光测距传感器串口
    Port = serial.Serial(LASER_PORT, LASER_BAUD_RATE)
    # 初始化ROS节点
    rospy.init_node("laser_inquire_node")
    # 创建服务端对象
    server = rospy.Service("laser_server", laser_ranging_srv, callback)
    rospy.loginfo("The server is successfunlly initialized.")
    rospy.loginfo("Wait for client request.")
    # 防止程序停止
    rospy.spin()
