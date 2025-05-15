#!/usr/bin/env python  
# -*- coding: utf-8 -*-  
  
import os  
import sys  
import socket  
import threading  
import time  
import json  
  
# 配置  
HOST = '127.0.0.1'  
PORT = 12013  
MAX_CLIENTS = 10  
GRADIENT_FILE = "gradient_info_p"  
EFFECTIVE_SEEDS_FILE = "effective_seeds.json"  
  
# 全局变量  
effective_seeds = []  
gradient_data = ""  
gradient_lock = threading.Lock()  
  
# 加载有效种子  
def load_effective_seeds():  
    global effective_seeds  
      
    if os.path.exists(EFFECTIVE_SEEDS_FILE):  
        try:  
            with open(EFFECTIVE_SEEDS_FILE, 'r') as f:  
                effective_seeds = json.load(f)  
        except Exception as e:  
            print(f"加载有效种子时出错: {e}")  
            effective_seeds = []  
  
# 保存有效种子  
def save_effective_seeds():  
    global effective_seeds  
      
    try:  
        with open(EFFECTIVE_SEEDS_FILE, 'w') as f:  
            json.dump(effective_seeds, f)  
    except Exception as e:  
        print(f"保存有效种子时出错: {e}")  
  
# 更新梯度数据  
def update_gradient_data():  
    global gradient_data  
      
    try:  
        if os.path.exists(GRADIENT_FILE):  
            with open(GRADIENT_FILE, 'r') as f:  
                with gradient_lock:  
                    gradient_data = f.read()  
    except Exception as e:  
        print(f"更新梯度数据时出错: {e}")  
  
# 梯度数据监控线程  
def gradient_monitor():  
    last_modified = 0  
      
    while True:  
        try:  
            if os.path.exists(GRADIENT_FILE):  
                current_modified = os.path.getmtime(GRADIENT_FILE)  
                if current_modified > last_modified:  
                    update_gradient_data()  
                    last_modified = current_modified  
        except Exception as e:  
            print(f"监控梯度文件时出错: {e}")  
          
        time.sleep(1)  
  
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
              
            if parts[0] == "GET_GRADIENT":  
                # 发送当前梯度信息  
                with gradient_lock:  
                    client_socket.sendall(gradient_data.encode('utf-8'))  
            elif parts[0] == "REPORT_EFFECTIVE":  
                # 记录有效种子  
                seed_path = parts[1]  if seed_path not in effective_seeds:  
                    effective_seeds.append(seed_path)  
                    save_effective_seeds()  
                client_socket.sendall(b"OK")  
            else:  
                client_socket.sendall(b"UNKNOWN_COMMAND")  
    except Exception as e:  
        print(f"处理客户端请求时出错: {e}")  
    finally:  
        client_socket.close()  
  
# 主函数  
def main():  
    # 加载有效种子  
    load_effective_seeds()  
      
    # 启动梯度监控线程  
    monitor_thread = threading.Thread(target=gradient_monitor)  
    monitor_thread.daemon = True  
    monitor_thread.start()  
      
    # 创建服务器套接字  
    server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)  
    server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)  
    server_socket.bind((HOST, PORT))  
    server_socket.listen(MAX_CLIENTS)  
      
    print(f"梯度服务器已在 {HOST}:{PORT} 上启动")  
      
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
