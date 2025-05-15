#!/usr/bin/env python  
# -*- coding: utf-8 -*-  
  
import os  
import sys  
import glob  
import math  
import time  
import keras  
import random  
import socket  
import threading  
import subprocess  
import numpy as np  
import tensorflow as tf  
import keras.backend as K  
from collections import Counter  
from tensorflow import set_random_seed  
from keras.models import Sequential, Model  
from keras.layers import Dense, Dropout, Activation, Input, Add, Multiply, Reshape  
from keras.callbacks import ModelCheckpoint, EarlyStopping  
from flask import Flask, request, jsonify  
  
# 配置  
HOST = '127.0.0.1'  
PORT = 12012  
GRADIENT_SERVER_PORT = 12013  
MAX_FILE_SIZE = 10000  
MAX_BITMAP_SIZE = 2000  
round_cnt = 0  
seed = 12  
np.random.seed(seed)  
random.seed(seed)  
set_random_seed(seed)  
seed_list = glob.glob('./seeds/*')  
new_seeds = glob.glob('./seeds/id_*')  
SPLIT_RATIO = len(seed_list)  
model_version = 0  
current_model = None  
effective_seeds = []  
  
# 获取二进制参数  
argvv = sys.argv[1:]  
  
# 自定义准确率度量  
def accur_1(y_true, y_pred):  
    y_pred_bin = K.round(y_pred)  
    return K.mean(K.equal(y_true, y_pred_bin), axis=-1)  
  
# 从AFL原始数据处理训练数据  
def enhanced_process_data():  
    global MAX_BITMAP_SIZE  
    global MAX_FILE_SIZE  
    global SPLIT_RATIO  
    global seed_list  
    global new_seeds  
  
    # 打乱训练样本  
    seed_list = glob.glob('./seeds/*')  
    seed_list.sort()  
    SPLIT_RATIO = len(seed_list)  
    rand_index = np.arange(SPLIT_RATIO)  
    np.random.shuffle(seed_list)  
    new_seeds = glob.glob('./seeds/id_*')  
  
    call = subprocess.check_output  
  
    # 获取MAX_FILE_SIZE  
    cwd = os.getcwd()  
    max_file_name = call(['ls', '-S', cwd + '/seeds/']).decode('utf8').split('\n')[0].rstrip('\n')  
    MAX_FILE_SIZE = os.path.getsize(cwd + '/seeds/' + max_file_name)  
  
    # 创建目录以保存标签、拼接种子、变长种子、崩溃和变异种子  
    os.path.isdir("./bitmaps/") or os.makedirs("./bitmaps")  
    os.path.isdir("./splice_seeds/") or os.makedirs("./splice_seeds")  
    os.path.isdir("./vari_seeds/") or os.makedirs("./vari_seeds")  
    os.path.isdir("./crashes/") or os.makedirs("./crashes")  
  
    # 获取原始位图  
    raw_bitmap = {}  
    tmp_cnt = []  
    out = ''  
    for f in seed_list:  
        tmp_list = []  
        try:  
            # 为strip的参数附加"-o tmp_file"以避免篡改测试二进制文件  
            if argvv[0] == './strip':  
                out = call(['./afl-showmap', '-q', '-e', '-o', '/dev/stdout', '-m', '512', '-t', '500'] + argvv + [f] + ['-o', 'tmp_file'])  
            else:  
                out = call(['./afl-showmap', '-q', '-e', '-o', '/dev/stdout', '-m', '512', '-t', '500'] + argvv + [f])  
        except subprocess.CalledProcessError:  
            print("发现崩溃")  
        for line in out.splitlines():  
            edge = line.split(b':')[0]  
            tmp_cnt.append(edge)  
            tmp_list.append(edge)  
        raw_bitmap[f] = tmp_list  
    counter = Counter(tmp_cnt).most_common()  
  
    # 将位图保存为单独的numpy标签  
    label = [int(f[0]) for f in counter]  
    bitmap = np.zeros((len(seed_list), len(label)))  
    for idx, i in enumerate(seed_list):  
        tmp = raw_bitmap[i]  
        for j in tmp:  
            if int(j) in label:  
                bitmap[idx][label.index((int(j)))] = 1  
  
    # 标签降维  
    fit_bitmap = np.unique(bitmap, axis=1)  
    print("数据维度" + str(fit_bitmap.shape))  
  
    # 保存训练数据  
    MAX_BITMAP_SIZE = fit_bitmap.shape[1]  
    for idx, i in enumerate(seed_list):  
        file_name = "./bitmaps/" + i.split('/')[-1]  
        np.save(file_name, fit_bitmap[idx])  
      
    return fit_bitmap  
  
# 构建带有残差连接和注意力机制的增强模型  
def build_enhanced_model():  
    global MAX_FILE_SIZE  
    global MAX_BITMAP_SIZE  
      
    num_classes = MAX_BITMAP_SIZE  
      
    # 输入层  
    input_layer = Input(shape=(MAX_FILE_SIZE,))  
      
    # 初始密集层  
    x = Dense(2048)(input_layer)  
    x = Activation('relu')(x)  
      
    # 添加残差块  
    for i in range(3):  
        x_shortcut = x  
        x = Dense(2048)(x)  
        x = Activation('relu')(x)  
        x = Dense(2048)(x)  
        x = Add()([x, x_shortcut])  # 残差连接  
        x = Activation('relu')(x)  
      
    # 添加注意力机制  
    attention = Dense(2048, activation='tanh')(x)  
    attention = Dense(1, activation='sigmoid')(attention)  
    attention = Reshape((2048,))(attention)  
    x = Multiply()([x, attention])  
      
    # 输出层  
    output = Dense(num_classes)(x)  
    output = Activation('sigmoid')(output)  
      
    # 创建模型  
    model = Model(inputs=input_layer, outputs=output)  
      
    # 编译模型  
    opt = keras.optimizers.Adam(lr=0.0001)  
    model.compile(loss='binary_crossentropy', optimizer=opt, metrics=[accur_1])  
      
    return model  
  
# 带有早停的增强训练函数  
def enhanced_train(model):  
    global SPLIT_RATIO  
    global seed_list  
      
    x_train = []  
    y_train = []  
      
    # 加载训练数据  
    for i in seed_list:  
        tmp_file = i.split('/')[-1]  
        tmp_bitmap = np.load('./bitmaps/' + tmp_file + '.npy')  
          
        # 读取种子文件  
        seed_data = open(i, 'rb').read()  
        if len(seed_data) < MAX_FILE_SIZE:  
            seed_data = seed_data + b'\0' * (MAX_FILE_SIZE - len(seed_data))  
        else:  
            seed_data = seed_data[:MAX_FILE_SIZE]  
          
        # 转换为numpy数组  
        seed_data = np.frombuffer(seed_data, dtype=np.uint8)  
        seed_data = seed_data.astype(np.float32) / 255.0  
          
        x_train.append(seed_data)  
        y_train.append(tmp_bitmap)  
      
    x_train = np.array(x_train)  
    y_train = np.array(y_train)  
      
    # 早停以防止过拟合  
    early_stopping = EarlyStopping(monitor='val_loss', patience=3, verbose=1)  
      
    # 训练模型  
    model.fit(  
        x_train, y_train,  
        epochs=10,  
        batch_size=32,  
        shuffle=True,  
        validation_split=0.1,  
        callbacks=[early_stopping]  
    )  
      
    return model  
  
# 自适应基于梯度的变异生成  
def adaptive_gen_mutate(model, edge_gain, sign):  
    global round_cnt  
    global effective_seeds  
    global seed_list  
    global new_seeds  
      
    # 根据边缘增益动态调整神经元数量  
    if edge_gain > 50:  
        edge_num = 300  # 发现较多新边缘时减少计算量  
    elif edge_gain > 20:  
        edge_num = 500  # 默认数量  
    else:  
        edge_num = 800  # 发现较少新边缘时增加计算量  
      
    tmp_list = []  
    print("#######debug" + str(round_cnt))  
      
    # 选择种子，优先选择有效种子  
    if round_cnt == 0:  
        new_seed_list = seed_list  
    else:  
        new_seed_list = new_seeds  
      
    # 优先选择之前产生好结果的种子  
    seed_candidates = list(set(new_seed_list) - set(effective_seeds))  
    if len(seed_candidates) < edge_num * 0.7:  
        # 如果候选不足，用随机种子补充  
        random_seeds = random.sample(seed_list, min(edge_num - len(seed_candidates), len(seed_list)))  
        selected_seeds = seed_candidates + random_seeds  
    else:  
        selected_seeds = random.sample(seed_candidates, min(edge_num, len(seed_candidates)))  
      
    # 处理选定的种子  
    for idx, i in enumerate(selected_seeds):  
        tmp_file = i.split('/')[-1]  
          
        # 读取种子文件  
        seed_data = open(i, 'rb').read()  
        if len(seed_data) < MAX_FILE_SIZE:  
            seed_data = seed_data + b'\0' * (MAX_FILE_SIZE - len(seed_data))  
        else:  
            seed_data = seed_data[:MAX_FILE_SIZE]  
          
        # 转换为numpy数组  
        seed_data = np.frombuffer(seed_data, dtype=np.uint8)  
        seed_data = seed_data.astype(np.float32) / 255.0  
          
        # 重塑用于预测  
        seed_data = seed_data.reshape(1, MAX_FILE_SIZE)  
          
        # 获取梯度  
        inp = model.input  
        out = model.output  
        gradients = K.gradients(out, inp)[0]  
        gradient_function = K.function([inp], [gradients])  
          
        # 计算梯度  
        grads = gradient_function([seed_data])[0][0]  
          
        # 找出重要位置  
        loc = np.argsort(np.absolute(grads))[-100:]  
        sign = np.sign(grads[loc])  
          
        # 保存梯度信息  
        tmp_list.append(str(list(loc)) + "|" + str(list(sign)) + "|" + i)  
      
    # 将梯度信息写入文件  
    with open("gradient_info_p", "w") as f:  
        for i in tmp_list:  
            f.write(i + "\n")  
      
    return tmp_list  
  
# 并行梯度生成  
def parallel_gen_grad(data):  
    global round_cnt  
    global model_version  
    global current_model  
      
    t0 = time.time()  
      
    # 创建线程同步锁  
    model_lock = threading.Lock()  
      
    # 训练过程函数  
    def training_process():  
        nonlocal current_model  
        enhanced_process_data()  
        model = build_enhanced_model()  
        enhanced_train(model)  
        with model_lock:  
            current_model = model  
            global model_version  
            model_version += 1  
      
    # 梯度生成过程函数  
    def gradient_process():  
        nonlocal current_model  
        last_used_version = 0  
        while True:  
            with model_lock:  
                if model_version > last_used_version and current_model is not None:  
                    model_copy = current_model  
                    last_used_version = model_version  
                elif current_model is None:  
                    time.sleep(1)  
                    continue  
                else:  
                    time.sleep(1)  
                    continue  
              
            # 根据数据前缀计算边缘增益  
            edge_gain = 30  # 默认值  
            if data[:5] == b"train":  
                edge_gain = 50  
            elif data[:5] == b"sloww":  
                edge_gain = 10  
            elif data[:5] == b"boost":  
                edge_gain = 100  
              
            # 使用复制的模型生成变异  
            adaptive_gen_mutate(model_copy, edge_gain, data[:5] == b"train")  
            break  
      
    # 启动并行线程  
    training_thread = threading.Thread(target=training_process)  
    gradient_thread = threading.Thread(target=gradient_process)  
      
    training_thread.start()  
    gradient_thread.start()  
      
    training_thread.join()  
    gradient_thread.join()  
      
    round_cnt = round_cnt + 1  
    print(f"总处理时间: {time.time() - t0}")  
  
# 用于实时梯度信息的梯度服务器  
def start_gradient_server():  
    server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)  
    server_socket.bind((HOST, GRADIENT_SERVER_PORT))  
    server_socket.listen(5)  
    print(f"梯度服务器已在端口 {GRADIENT_SERVER_PORT} 上启动")  
      
    while True:  
        client_socket, addr = server_socket.accept()  
        print(f"梯度客户端已连接: {addr}")  
          
        # 在单独的线程中处理客户端  
        client_thread = threading.Thread(target=handle_gradient_client, args=(client_socket,))  
        client_thread.daemon = True  
        client_thread.start()  
  
# 处理梯度客户端连接  
def handle_gradient_client(client_socket):  
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
                with open("gradient_info_p", "r") as f:  
                    gradient_data = f.read()  
                client_socket.sendall(gradient_data.encode('utf-8'))  
            elif parts[0] == "REPORT_EFFECTIVE":  
                # 记录有效种子  
                seed_path = parts[1]  
                if seed_path not in effective_seeds:  
                    effective_seeds.append(seed_path)  
                client_socket.sendall(b"OK")  
    except Exception as e:  
        print(f"处理梯度客户端时出错: {e}")  
    finally:  
        client_socket.close()  
  
# 智能种子拼接  
def intelligent_splice(seed1, seed2, idx):  
    # 读取两个种子文件  
    data1 = open(seed1, 'rb').read()  
    data2 = open(seed2, 'rb').read()  
      
    # 确定拼接点  
    splice_point = random.randint(0, min(len(data1), len(data2)))  
      
    # 创建拼接种子  
    spliced_data = data1[:splice_point] + data2[splice_point:]  
      
    # 保存拼接种子  
    output_path = f'./splice_seeds/tmp_{idx}'  
    with open(output_path, 'wb') as f:  
        f.write(spliced_data)  
      
    return output_path  
  
# 覆盖率监控器类  
class CoverageMonitor:  
    def __init__(self):  
        self.previous_coverage = 0  
        self.coverage_history = []  
        self.path_depth_history = []  
        self.memory_access_history = []  
      
    def analyze_coverage(self, coverage_data):  
        # 提取覆盖率指标  
        edge_coverage = coverage_data.get('edge_coverage', 0)  
        path_depth = coverage_data.get('path_depth', 0)  
        memory_access = coverage_data.get('memory_access', 0)  
          
        # 计算增益  
        edge_gain = edge_coverage - self.previous_coverage  
        self.previous_coverage = edge_coverage  
          
        # 更新历史  
        self.coverage_history.append(edge_coverage)  
        self.path_depth_history.append(path_depth)  
        self.memory_access_history.append(memory_access)  
          
        # 计算趋势  
        trend = 0  
        if len(self.coverage_history) > 5:  
            recent = self.coverage_history[-5:]  
            if recent[-1] > recent[0]:  
                trend = 1  # 正向趋势  
            elif recent[-1] < recent[0]:  
                trend = -1  # 负向趋势  
          
        return {  
            'edge_coverage': edge_coverage,  
            'edge_gain': edge_gain,  
            'path_depth': path_depth,  
            'memory_access': memory_access,  
            'trend': trend  
        }  
  
# 分布式协调器  
class DistributedCoordinator:  
    def __init__(self, host='0.0.0.0', port=8080):  
        self.host = host  
        self.port = port  
        self.seed_pool = []  
        self.result_collector = {}  
        self.clients = {}  
        self.app = Flask(__name__)  
        self.setup_routes()  
      
    def setup_routes(self):  
        @self.app.route('/get_seed', methods=['GET'])  
        def get_seed():  
            client_id = request.args.get('client_id', 'unknown')  
            if not self.seed_pool:  
                return jsonify({'status': 'empty'})  
              
            seed = self.seed_pool.pop(0)  
            return jsonify({'status': 'ok', 'seed': seed})  
          
        @self.app.route('/submit_result', methods=['POST'])  
        def submit_result():  
            data = request.json  
            client_id = data.get('client_id', 'unknown')  
            result = data.get('result', {})  
              
            if client_id not in self.clients:  
                self.clients[client_id] = {'results': 0, 'new_coverage': 0}  
              
            self.clients[client_id]['results'] += 1  
              
            if result.get('new_coverage', False):  
                self.clients[client_id]['new_coverage'] += 1  
                self.seed_pool.append(result.get('seed', ''))  
              
            return jsonify({'status': 'ok'})  
          
        @self.app.route('/get_training_data', methods=['GET'])  
        def get_training_data():  
            return jsonify({'status': 'ok', 'seeds': self.seed_pool})  
          
        @self.app.route('/submit_gradient', methods=['POST'])  
        def submit_gradient():  
            data = request.json  
            gradient_info = data.get('gradient_info', [])  
              
            # 存储梯度信息供模糊测试引擎使用  
            with open("distributed_gradient_info", "w") as f:  
                for item in gradient_info:  
                    f.write(item + "\n")  
              
            return jsonify({'status': 'ok'})  
          
        @self.app.route('/status', methods=['GET'])  
        def status():  
            return jsonify({  
                'status': 'ok',  
                'clients': self.clients,  
                'seed_pool_size': len(self.seed_pool)  
            })  
      
    def start(self):  
        self.app.run(host=self.host, port=self.port)  
  
# 增强型服务器设置  
def setup_enhanced_server():  
    # 在单独的线程中启动梯度服务器  
    gradient_thread = threading.Thread(target=start_gradient_server)  
    gradient_thread.daemon = True  
    gradient_thread.start()  
      
    # 主通信套接字  
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)  
    sock.bind((HOST, PORT))  
    sock.listen(1)  
    print(f"神经网络服务器已在端口 {PORT} 上启动")  
      
    # 接受来自模糊测试引擎的连接  
    conn, addr = sock.accept()  
    print('已连接模糊测试引擎: ' + str(addr))  
      
    # 初始训练  
    parallel_gen_grad(b"train")  
    conn.sendall(b"start")  
      
    # 主通信循环  
    while True:  
        data = conn.recv(1024)  
        if not data:  
            break  
        else:  
            parallel_gen_grad(data)  
            conn.sendall(b"start")  
      
    conn.close()  
  
# 主函数  
if __name__ == '__main__':  
    # 检查是否以分布式模式运行  
    if len(sys.argv) > 1 and sys.argv[1] == '--distributed':  
        coordinator = DistributedCoordinator()  
        coordinator.start()  
    else:  
        # 普通模式  
        setup_enhanced_server()
  
