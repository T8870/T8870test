#!/bin/bash  
  
# 增强型NEUZZ构建脚本  
  
# 编译模糊测试引擎  
echo "编译增强型模糊测试引擎..."  
gcc -O3 -funroll-loops ./src/enhanced_neuzz.c -o enhanced_neuzz  
  
# 检查Python依赖  
echo "检查Python依赖..."  
pip install -r requirements.txt  
  
# 创建必要的目录  
echo "创建目录结构..."  
mkdir -p seeds  
mkdir -p crashes  
mkdir -p timeouts  
mkdir -p bitmaps  
mkdir -p splice_seeds  
mkdir -p vari_seeds  
mkdir -p visualization  
mkdir -p crash_analysis  
  
echo "构建完成！"
