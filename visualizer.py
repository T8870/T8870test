#!/usr/bin/env python  
# -*- coding: utf-8 -*-  
  
import os  
import sys  
import json  
import time  
import argparse  
import matplotlib.pyplot as plt  
import numpy as np  
from matplotlib.animation import FuncAnimation  
  
# 配置  
COVERAGE_DATA_FILE = "coverage_data.json"  
OUTPUT_DIR = "./visualization"  
  
# 加载覆盖率数据  
def load_coverage_data(file_path=COVERAGE_DATA_FILE):  
    if os.path.exists(file_path):  
        with open(file_path, 'r') as f:  
            return json.load(f)  
    return []  
  
# 保存覆盖率数据  
def save_coverage_data(data, file_path=COVERAGE_DATA_FILE):  
    with open(file_path, 'w') as f:  
        json.dump(data, f, indent=2)  
  
# 添加新的覆盖率数据点  
def add_coverage_data_point(edge_coverage, path_depth, memory_diversity):  
    data = load_coverage_data()  
    data.append({  
        'timestamp': time.time(),  
        'edge_coverage': edge_coverage,  
        'path_depth': path_depth,  
        'memory_diversity': memory_diversity  
    })  
    save_coverage_data(data)  
  
# 生成静态覆盖率图表  
def generate_static_coverage_chart(output_path=None):  
    data = load_coverage_data()  
    if not data:  
        print("没有可用的覆盖率数据")  
        return  
      
    # 创建输出目录  
    os.makedirs(OUTPUT_DIR, exist_ok=True)  
      
    # 提取数据  
    timestamps = [entry['timestamp'] for entry in data]  
    edge_coverage = [entry['edge_coverage'] for entry in data]  
    path_depth = [entry['path_depth'] for entry in data]  
    memory_diversity = [entry['memory_diversity'] for entry in data]  
      
    # 转换时间戳为相对时间（小时）  
    start_time = timestamps[0]  
    relative_time = [(t - start_time) / 3600 for t in timestamps]  
      
    # 创建图表  
    plt.figure(figsize=(12, 8))  
      
    # 边缘覆盖率  
    plt.subplot(3, 1, 1)  
    plt.plot(relative_time, edge_coverage, 'b-', label='边缘覆盖率')  
    plt.title('边缘覆盖率随时间变化')  
    plt.xlabel('时间（小时）')  
    plt.ylabel('覆盖的边缘数量')  
    plt.grid(True)  
    plt.legend()  
      
    # 路径深度  
    plt.subplot(3, 1, 2)  
    plt.plot(relative_time, path_depth, 'g-', label='路径深度')  
    plt.title('路径深度随时间变化')  
    plt.xlabel('时间（小时）')  
    plt.ylabel('平均路径深度')  
    plt.grid(True)  
    plt.legend()  
      
    # 内存多样性  
    plt.subplot(3, 1, 3)  
    plt.plot(relative_time, memory_diversity, 'r-', label='内存多样性')  
    plt.title('内存多样性随时间变化')  
    plt.xlabel('时间（小时）')  
    plt.ylabel('内存访问多样性')  
    plt.grid(True)  
    plt.legend()  
      
    plt.tight_layout()  
      
    # 保存图表  
    if output_path:  
        plt.savefig(output_path)  
    else:  
        plt.savefig(f"{OUTPUT_DIR}/coverage_chart_{int(time.time())}.png")  
      
    plt.close()  
  
# 生成动态覆盖率图表  
def generate_animated_coverage_chart(output_path=None):  
    data = load_coverage_data()  
    if not data:  
        print("没有可用的覆盖率数据")  
        return  
      
    # 创建输出目录  
    os.makedirs(OUTPUT_DIR, exist_ok=True)  
      
    # 提取数据  
    timestamps = [entry['timestamp'] for entry in data]  
    edge_coverage = [entry['edge_coverage'] for entry in data]  
    path_depth = [entry['path_depth'] for entry in data]  
    memory_diversity = [entry['memory_diversity'] for entry in data]  
      
    # 转换时间戳为相对时间（小时）  
    start_time = timestamps[0]  
    relative_time = [(t - start_time) / 3600 for t in timestamps]  
      
    # 创建图表  
    fig, (ax1, ax2, ax3) = plt.subplots(3, 1, figsize=(12, 8))  
      
    # 初始化空线条  
    line1, = ax1.plot([], [], 'b-', label='边缘覆盖率')  
    line2, = ax2.plot([], [], 'g-', label='路径深度')  
    line3, = ax3.plot([], [], 'r-', label='内存多样性')  
      
    # 设置标题和标签  
    ax1.set_title('边缘覆盖率随时间变化')  
    ax1.set_xlabel('时间（小时）')  
    ax1.set_ylabel('覆盖的边缘数量')  
    ax1.grid(True)  
    ax1.legend()  
      
    ax2.set_title('路径深度随时间变化')  
    ax2.set_xlabel('时间（小时）')  
    ax2.set_ylabel('平均路径深度')  
    ax2.grid(True)  
    ax2.legend()  
      
    ax3.set_title('内存多样性随时间变化')  
    ax3.set_xlabel('时间（小时）')  
    ax3.set_ylabel('内存访问多样性')  
    ax3.grid(True)  
    ax3.legend()  
      
    # 设置轴范围  
    ax1.set_xlim(0, max(relative_time))  
    ax1.set_ylim(0, max(edge_coverage) * 1.1)  
      
    ax2.set_xlim(0, max(relative_time))  
    ax2.set_ylim(0, max(path_depth) * 1.1)  
      
    ax3.set_xlim(0, max(relative_time))  
    ax3.set_ylim(0, max(memory_diversity) * 1.1)  
      
    plt.tight_layout()  
      
    # 动画更新函数  
    def update(frame):  
        # 更新数据  
        x_data = relative_time[:frame]  
        y1_data = edge_coverage[:frame]  
        y2_data = path_depth[:frame]  
        y3_data = memory_diversity[:frame]  
          
        # 更新线条  
        line1.set_data(x_data, y1_data)  
        line2.set_data(x_data, y2_data)  
        line3.set_data(x_data, y3_data)  
          
        return line1, line2, line3  
      
    # 创建动画  
    ani = FuncAnimation(fig, update, frames=len(relative_time), blit=True)  
      
    # 保存动画  
    if output_path:  
        ani.save(output_path, writer='ffmpeg', fps=10)  
    else:  
        ani.save(f"{OUTPUT_DIR}/coverage_animation_{int(time.time())}.mp4", writer='ffmpeg', fps=10)  
      
    plt.close()  
  
# 主函数  
def main():  
    parser = argparse.ArgumentParser(description='NEUZZ覆盖率可视化工具')  
    parser.add_argument('--add', action='store_true', help='添加新的覆盖率数据点')  
    parser.add_argument('--edge', type=int, help='边缘覆盖率')  
    parser.add_argument('--path', type=float, help='路径深度')  
    parser.add_argument('--memory', type=int, help='内存多样性')  
    parser.add_argument('--static', action='store_true', help='生成静态覆盖率图表')  
    parser.add_argument('--animate', action='store_true', help='生成动态覆盖率图表')  
    parser.add_argument('--output', help='输出文件路径')  
      
    args = parser.parse_args()  
      
    if args.add:  
        if args.edge is None or args.path is None or args.memory is None:  
            parser.error("添加数据点需要指定--edge、--path和--memory参数")  
        add_coverage_data_point(args.edge, args.path, args.memory)  
        print("已添加覆盖率数据点")  
      
    if args.static:  
        generate_static_coverage_chart(args.output)  
        print("已生成静态覆盖率图表")  
      
    if args.animate:  
        generate_animated_coverage_chart(args.output)  
        print("已生成动态覆盖率图表")  
      
    if not (args.add or args.static or args.animate):  
        parser.print_help()  
  
if __name__ == "__main__":  
    main()
