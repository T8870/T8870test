#!/usr/bin/env python  
# -*- coding: utf-8 -*-  
  
import os  
import sys  
import glob  
import subprocess  
import argparse  
import json  
  
# 配置  
CRASHES_DIR = "./crashes"  
ANALYSIS_DIR = "./crash_analysis"  
  
# 分析崩溃  
def analyze_crash(crash_file, target_program, args):  
    try:  
        # 创建分析目录  
        os.makedirs(ANALYSIS_DIR, exist_ok=True)  
          
        # 获取崩溃文件名（不含路径）  
        crash_name = os.path.basename(crash_file)  
          
        # 准备GDB命令  
        gdb_commands = [  
            "set pagination off",  
            "set logging on",  
            f"set logging file {ANALYSIS_DIR}/{crash_name}.log",  
            "run",  
            "bt full",  
            "info registers",  
            "quit"  
        ]  
          
        # 创建GDB命令文件  
        with open(f"{ANALYSIS_DIR}/gdb_commands.txt", "w") as f:  
            for cmd in gdb_commands:  
                f.write(cmd + "\n")  
          
        # 替换参数中的@@为崩溃文件路径  
        cmd_args = []  
        for arg in args:  
            if arg == "@@":  
                cmd_args.append(crash_file)  
            else:  
                cmd_args.append(arg)  
          
        # 运行GDB  
      cmd = ["gdb", "--batch", "-x", f"{ANALYSIS_DIR}/gdb_commands.txt", target_program] + cmd_args  
          
        # 执行命令  
        subprocess.run(cmd, check=True)  
          
        # 分析崩溃日志  
        crash_log_path = f"{ANALYSIS_DIR}/{crash_name}.log"  
        if os.path.exists(crash_log_path):  
            with open(crash_log_path, 'r') as f:  
                log_content = f.read()  
              
            # 提取关键信息  
            crash_info = {  
                'crash_file': crash_file,  
                'target_program': target_program,  
                'args': args,  
                'timestamp': time.time(),  
                'backtrace': extract_backtrace(log_content),  
                'registers': extract_registers(log_content),  
                'crash_type': determine_crash_type(log_content)  
            }  
              
            # 保存分析结果  
            with open(f"{ANALYSIS_DIR}/{crash_name}.json", 'w') as f:  
                json.dump(crash_info, f, indent=2)  
              
            return crash_info  
        else:  
            print(f"无法生成崩溃日志: {crash_log_path}")  
            return None  
    except Exception as e:  
        print(f"分析崩溃时出错: {e}")  
        return None  
  
# 从日志中提取回溯信息  
def extract_backtrace(log_content):  
    backtrace = []  
    in_backtrace = False  
      
    for line in log_content.splitlines():  
        if line.startswith('#'):  
            in_backtrace = True  
            backtrace.append(line)  
        elif in_backtrace and not line.strip():  
            in_backtrace = False  
      
    return backtrace  
  
# 从日志中提取寄存器信息  
def extract_registers(log_content):  
    registers = {}  
    in_registers = False  
      
    for line in log_content.splitlines():  
        if line.startswith('rax') or line.startswith('eax'):  
            in_registers = True  
          
        if in_registers:  
            parts = line.split()  
            if len(parts) >= 2:  
                reg_name = parts[0]  
                reg_value = parts[1]  
                registers[reg_name] = reg_value  
              
            if not line.strip():  
                in_registers = False  
      
    return registers  
  
# 确定崩溃类型  
def determine_crash_type(log_content):  
    if 'SIGSEGV' in log_content:  
        return 'SEGMENTATION_FAULT'  
    elif 'SIGABRT' in log_content:  
        return 'ABORT'  
    elif 'SIGFPE' in log_content:  
        return 'FLOATING_POINT_EXCEPTION'  
    elif 'SIGILL' in log_content:  
        return 'ILLEGAL_INSTRUCTION'  
    else:  
        return 'UNKNOWN'  
  
# 主函数  
def main():  
    parser = argparse.ArgumentParser(description='分析NEUZZ发现的崩溃')  
    parser.add_argument('--crash', help='要分析的崩溃文件路径')  
    parser.add_argument('--target', required=True, help='目标程序路径')  
    parser.add_argument('--args', nargs='*', default=[], help='目标程序参数')  
    parser.add_argument('--all', action='store_true', help='分析所有崩溃')  
      
    args = parser.parse_args()  
      
    if args.all:  
        # 分析所有崩溃  
        crash_files = glob.glob(f"{CRASHES_DIR}/*")  
        for crash_file in crash_files:  
            print(f"分析崩溃: {crash_file}")  
            analyze_crash(crash_file, args.target, args.args)  
    elif args.crash:  
        # 分析单个崩溃  
        analyze_crash(args.crash, args.target, args.args)  
    else:  
        parser.print_help()  
  
if __name__ == "__main__":  
    main()
