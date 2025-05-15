#!/usr/bin/env python  
# -*- coding: utf-8 -*-  
  
import os  
import sys  
import time  
import json  
import socket  
import threading  
import numpy as np  
from collections import deque  
  
# 配置  
HOST = '127.0.0.1'  
PORT = 12014  
SHM_PATH = "/dev/shm/"  
HISTORY_SIZE = 100  
  
# 全局变量  
coverage_history = deque(maxlen=HISTORY_SIZE)  
path_depth_history = deque(maxlen=HISTORY_SIZE)  
memory_diversity_history = deque(maxlen=HISTORY_SIZE)  
monitor_lock = threading.Lock()  
  
# 分析覆盖率数据  
def analyze_coverage(coverage_data):  
    with monitor_lock:  
        # 提取覆盖率指标  
        edge_coverage = coverage_data.get('edge_coverage', 0)  
        path_depth = coverage_data.get('path_depth', 0)  
        memory_diversity = coverage_data.get('memory_access', 0)  
          
        # 更新历史  
        coverage_history.append(edge_coverage)  
        path_depth_history.append(path_depth)  
        memory_diversity_history.append(memory_diversity)  
          
        # 计算增益  
        edge_gain = 0  
        if len(coverage_history) > 1:  
            edge_gain = edge_coverage - coverage_history[-2]  
          
        # 计算趋势  
        trend = 0  
        if len(coverage_history) > 5:  
            recent = list(coverage_history)[-5:]  
            if recent[-1] > recent[0]:  
                trend = 1  # 正向趋势  
            elif recent[-1] < recent[0]:  
                trend = -1  # 负向趋势  
          
        # 计算波动性  
        volatility = 0  
        if len(coverage_history) > 10:  
            recent = list(coverage_history)[-10:]  
            volatility = np.std(recent) / max(np.mean(recent), 1)  
          
        return {  
            'edge_coverage': edge_coverage,  
            'edge_gain': edge_gain,  
            'path_depth': path_depth,  
            'memory_diversity': memory_diversity,  
            'trend': trend,  
            'volatility': volatility,  
            'timestamp': time.time()  
        }  
  
# 监控共享内存  
def monitor_shm(shm_id):  
    try:  
        # 附加到共享内存  
        import mmap  
          
        shm_file = f"{SHM_PATH}{shm_id}"  
        if not os.path.exists(shm_file):  
            print(f"共享内存文件不存在: {shm_file}")  
            return None  
          
        with open(shm_file, "r+b") as f:  
            mm = mmap.mmap(f.fileno(), 0)  
              
            # 读取覆盖率数据  
            data = mm.read()  
              
            # 计算边缘覆盖率  
            edge_coverage = sum(1 for b in data[:65536] if b != 0)  
              
            # 计算路径深度  
            path_depth = sum(data[:65536]) / max(edge_coverage, 1)  
              
            # 计算内存访问多样性  
            memory_diversity = sum(1 for b in data[65536:] if b != 0)  
              
            return {  
                'edge_coverage': edge_coverage,  
                'path_depth': path_depth,  
                'memory_access': memory_diversity  
            }  
    except Exception as e:  
        print(f"监控共享内存时出错: {e}")  
        return None  
  
# 处理客户端连接  
def handle_client(client_socket, addr):  
    print(f"客户端已连接: {addr}")  
      
    try:  
        while True:  
            # 接收请求  
            data = client_socket.recv(1024)  
            if not data:  
                break  
              
            # 解析请求  
            request = data.decode('utf-8').strip()  
            parts = request.split('|')  
              
            if parts[0] == "GET_ANALYSIS":  
                # 获取共享内存ID  
                if len(parts) > 1:  
                    shm_id = parts[1]  
                    coverage_data = monitor_shm(shm_id)  
                    if coverage_data:  
                        analysis = analyze_coverage(coverage_data)  
                        client_socket.sendall(json.dumps(analysis).encode('utf-8'))  
                    else:  
                        client_socket.sendall(b"ERROR: Failed to monitor shared memory")  
                else:  
                    client_socket.sendall(b"ERROR: Missing shared memory ID")  
            elif parts[0] == "GET_HISTORY":  
                # 返回历史数据  
                history = {  
                    'coverage': list(coverage_history),  
                    'path_depth': list(path_depth_history),  
                    'memory_diversity': list(memory_diversity_history)  
                }  
                client_socket.sendall(json.dumps(history).encode('utf-8'))  
            else:  
                client_socket.sendall(b"UNKNOWN_COMMAND")  
    except Exception as e:  
        print(f"处理客户端请求时出错: {e}")  
    finally:  
        client_socket.close()  
  
# 主函数  
def main():  
    # 创建服务器套接字  
    server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)  
    server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)  
    server_socket.bind((HOST, PORT))  
    server_socket.listen(5)  
      
    print(f"覆盖率监控器已在 {HOST}:{PORT} 上启动")  
      
    try:  
        while True:  
            # 接受客户端连接  
            client_socket, addr = server_socket.accept()  
              
            # 在新线程中处理客户端  
            client_thread = threading.Thread(target=handle_client, args=(client_socket, addr))  
            client_thread.daemon = True  
            client_thread.start()  
    except KeyboardInterrupt:  
        print("服务器正在关闭...")  
    finally:  
        server_socket.close()  
  
if __name__ == "__main__":  
    main()
