#!/bin/bash  
  
# 增强型NEUZZ停止脚本  
  
# 检查PID文件  
if [ ! -f .pid ]; then  
    echo "找不到PID文件，可能没有运行中的组件"  
    exit 1  
fi  
  
# 读取PID  
read GRADIENT_PID MONITOR_PID NN_PID NEUZZ_PID < .pid  
  
# 停止所有组件  
echo "停止模糊测试引擎 (PID: $NEUZZ_PID)..."  
kill -TERM $NEUZZ_PID 2>/dev/null || echo "模糊测试引擎已停止"  
  
echo "停止神经网络模块 (PID: $NN_PID)..."  
kill -TERM $NN_PID 2>/dev/null || echo "神经网络模块已停止"  
  
echo "停止覆盖率监控器 (PID: $MONITOR_PID)..."  
kill -TERM $MONITOR_PID 2>/dev/null || echo "覆盖率监控器已停止"  
  
echo "停止梯度服务器 (PID: $GRADIENT_PID)..."  
kill -TERM $GRADIENT_PID 2>/dev/null || echo "梯度服务器已停止"  
  
# 删除PID文件  
rm -f .pid  
  
echo "所有组件已停止！"
