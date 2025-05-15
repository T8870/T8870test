#!/usr/bin/env python  
# -*- coding: utf-8 -*-  
  
import os  
import sys  
import time  
import json  
import threading  
from flask import Flask, request, jsonify  
  
# 配置  
HOST = '0.0.0.0'  
PORT = 8080  
SEED_POOL_FILE = "seed_pool.json"  
CLIENTS_FILE = "clients.json"  
GRADIENT_INFO_FILE = "distributed_gradient_info"  
  
# 全局变量  
seed_pool = []  
clients = {}  
result_collector = {}  
data_lock = threading.Lock()  
  
# 加载数据  
def load_data():  
    global seed_pool, clients  
      
    try:  
        if os.path.exists(SEED_POOL_FILE):  
            with open(SEED_POOL_FILE, 'r') as f:  
                seed_pool = json.load(f)  
          
        if os.path.exists(CLIENTS_FILE):  
            with open(CLIENTS_FILE, 'r') as f:  
                clients = json.load(f)  
    except Exception as e:  
        print(f"加载数据时出错: {e}")  
  
# 保存数据  
def save_data():  
    try:  
        with open(SEED_POOL_FILE, 'w') as f:  
            json.dump(seed_pool, f)  
          
        with open(CLIENTS_FILE, 'w') as f:  
            json.dump(clients, f)  
    except Exception as e:  
        print(f"保存数据时出错: {e}")  
  
# 定期保存数据的线程  
def autosave_thread():  
    while True:  
        with data_lock:  
            save_data()  
        time.sleep(60)  # 每分钟保存一次  
  
# 创建Flask应用  
app = Flask(__name__)  
  
# 路由：获取种子  
@app.route('/get_seed', methods=['GET'])  
def get_seed():  
    client_id = request.args.get('client_id', 'unknown')  
      
    with data_lock:  
        if not seed_pool:  
            return jsonify({'status': 'empty'})  
          
        seed = seed_pool.pop(0)  
        return jsonify({'status': 'ok', 'seed': seed})  
  
# 路由：提交结果  
@app.route('/submit_result', methods=['POST'])  
def submit_result():  
    data = request.json  
    client_id = data.get('client_id', 'unknown')  
    result = data.get('result', {})  
      
    with data_lock:  
        if client_id not in clients:  
            clients[client_id] = {'results': 0, 'new_coverage': 0}  
          
        clients[client_id]['results'] += 1  
          
        if result.get('new_coverage', False):  
            clients[client_id]['new_coverage'] += 1  
            seed_path = result.get('seed', '')  
            if seed_path and seed_path not in seed_pool:  
                seed_pool.append(seed_path)  
      
    return jsonify({'status': 'ok'})  
  
# 路由：获取训练数据  
@app.route('/get_training_data', methods=['GET'])  
def get_training_data():  
    with data_lock:  
        return jsonify({'status': 'ok', 'seeds': seed_pool})  
  
# 路由：提交梯度信息  
@app.route('/submit_gradient', methods=['POST'])  
def submit_gradient():  
    data = request.json  
    gradient_info = data.get('gradient_info', [])  
      
    try:  
        with open(GRADIENT_INFO_FILE, 'w') as f:  
            for item in gradient_info:  
                f.write(item + "\n")  
    except Exception as e:  
        print(f"保存梯度信息时出错: {e}")  
        return jsonify({'status': 'error', 'message': str(e)})  
      
    return jsonify({'status': 'ok'})  
  
# 路由：获取状态  
@app.route('/status', methods=['GET'])  
def status():  
    with data_lock:  
        return jsonify({  
            'status': 'ok',  
            'clients': clients,  
            'seed_pool_size': len(seed_pool)  
        })  
  
# 路由：添加种子  
@app.route('/add_seed', methods=['POST'])  
def add_seed():  
    data = request.json  
    seed_path = data.get('seed_path', '')  
      
    if not seed_path:  
        return jsonify({'status': 'error', 'message': 'Missing seed path'})  
      
    with data_lock:  
        if seed_path not in seed_pool:  
            seed_pool.append(seed_path)  
      
    return jsonify({'status': 'ok'})  
  
# 路由：重置  
@app.route('/reset', methods=['POST'])  
def reset():  
    with data_lock:  
        seed_pool.clear()  
        clients.clear()  
        save_data()  
      
    return jsonify({'status': 'ok'})  
  
# 主函数  
def main():  
    # 加载数据  
    load_data()  
      
    # 启动自动保存线程  
    save_thread = threading.Thread(target=autosave_thread)  
    save_thread.daemon = True  
    save_thread.start()  
      
    # 启动Flask应用  
    app.run(host=HOST, port=PORT)  
  
if __name__ == "__main__":  
    main()
