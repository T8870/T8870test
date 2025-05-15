# 增强型NEUZZ使用指南  
  
## 安装  
  
1. 克隆仓库：  
   ```bash  
   git clone https://github.com/yourusername/enhanced-neuzz.git  
   cd enhanced-neuzz
构建项目：
./build.sh
基本用法
单机模式
启动神经网络模块：

python src/enhanced_nn.py ./target_program [arguments]
启动模糊测试引擎：

./enhanced_neuzz -i neuzz_in -o seeds -l file_length ./target_program [arguments] @@
分布式模式
启动协调器：

python src/coordinator.py
在每台机器上启动神经网络模块：

python src/enhanced_nn.py --distributed
在每台机器上启动模糊测试引擎：

./enhanced_neuzz -i neuzz_in -o seeds -l file_length --distributed ./target_program [arguments] @@
高级功能
覆盖率监控
启动覆盖率监控器：

python src/coverage_monitor.py
崩溃分析
分析发现的崩溃：

python src/crash_analyzer.py --target ./target_program --all
覆盖率可视化
生成覆盖率图表：

python src/visualizer.py --static
配置
可以通过修改 config/default.conf 文件来自定义系统行为。主要配置选项包括：

神经网络参数
模糊测试引擎参数
变异策略
分布式设置
故障排除
如果遇到问题，请检查：

共享内存设置是否正确
网络连接是否正常
目标程序是否可执行
初始种子是否有效
