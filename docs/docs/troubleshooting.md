## 12. 项目启动脚本 (run.sh)  [header-5](#header-5)
  
```bash  
#!/bin/bash  
  
# 增强型NEUZZ启动脚本  
  
# 加载配置  
source config/default.conf  
  
# 检查参数  
if [ $# -lt 1 ]; then  
    echo "用法: $0 <目标程序> [参数...]"  
    exit 1  
fi  
  
TARGET_PROGRAM=$1  
shift  
ARGS=$@  
  
# 创建日志目录  
mkdir -p logs  
  
# 启动梯度服务器  
echo "启动梯度服务器..."  
python src/gradient_server.py > logs/gradient_server.log 2>&1 &  
GRADIENT_PID=$!  
echo "梯度服务器PID: $GRADIENT_PID"  
  
# 启动覆盖率监控器  
echo "启动覆盖率监控器..."  
python src/coverage_monitor.py > logs/coverage_monitor.log 2>&1 &  
MONITOR_PID=$!  
echo "覆盖率监控器PID: $MONITOR_PID"  
  
# 启动神经网络模块  
echo "启动神经网络模块..."  
python src/enhanced_nn.py $TARGET_PROGRAM $ARGS > logs/nn.log 2>&1 &  
NN_PID=$!  
echo "神经网络模块PID: $NN_PID"  
  
# 等待神经网络模块启动  
echo "等待神经网络模块启动..."  
sleep 5  
  
# 启动模糊测试引擎  
echo "启动模糊测试引擎..."  
./enhanced_neuzz -i neuzz_in -o seeds -l $MAX_FILE_SIZE $TARGET_PROGRAM $ARGS @@ > logs/neuzz.log 2>&1 &  
NEUZZ_PID=$!  
echo "模糊测试引擎PID: $NEUZZ_PID"  
  
# 保存PID  
echo "$GRADIENT_PID $MONITOR_PID $NN_PID $NEUZZ_PID" > .pid  
  
echo "所有组件已启动！"  
echo "查看日志: tail -f logs/*.log"  
echo "停止所有组件: ./stop.sh"  
