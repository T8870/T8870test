/*  
 * 增强型NEUZZ - 神经网络辅助的模糊测试器，具有改进的架构  
 * 基于Dongdong She的原始NEUZZ  
 */  
  
#define _GNU_SOURCE  
#include <stdio.h>  
#include <stdlib.h>  
#include <unistd.h>  
#include <string.h>  
#include <signal.h>  
#include <fcntl.h>  
#include <errno.h>  
#include <time.h>  
#include <sys/mman.h>  
#include <sys/wait.h>  
#include <sys/time.h>  
#include <sys/shm.h>  
#include <sys/stat.h>  
#include <sys/types.h>  
#include <sys/resource.h>  
#include <sys/socket.h>  
#include <netinet/in.h>  
#include <arpa/inet.h>  
#include <dirent.h>  
  
/* 可配置设置 */  
#define FORKSRV_FD 198  
#define MAP_SIZE_POW2 16  
#define MAP_SIZE (1 << MAP_SIZE_POW2)  
#define ENHANCED_MAP_SIZE (MAP_SIZE * 2)  // 扩展的多维覆盖率映射  
#define TMOUT_MULTIPLIER 2  
#define MAX_FILE 1024 * 1024  
#define PRIORITY_QUEUE_SIZE 100  
#define HOST "127.0.0.1"  
#define PORT 12012  
#define GRADIENT_PORT 12013  
#define MAX_MUTATION_RETRY 10  
  
/* 全局变量 */  
static u8* trace_bits;                   // 与目标程序共享的内存  
static u8* enhanced_trace_bits;          // 用于多维覆盖率的扩展共享内存  
static u8* out_buf, *out_buf1, *out_buf2, *out_buf3;  // 变异缓冲区  
static u32 queued_paths,                 // 队列中的测试用例总数  
           cur_path,                     // 当前测试用例编号  
           stage_cur, stage_max;         // 模糊测试阶段进度  
static u64 total_execs;                  // 总执行次数  
static u32 cpu_core_count;               // CPU核心数  
static s32 forksrv_pid,                  // Fork服务器的PID  
           fsrv_ctl_fd,                  // Fork服务器控制管道  
           fsrv_st_fd;                   // Fork服务器状态管道  
static u32 exec_tmout = 1000;            // 执行超时（毫秒）  
static u8  virgin_bits[MAP_SIZE],        // 尚未被模糊测试触及的区域  
           virgin_hang[MAP_SIZE],        // 尚未在挂起中看到的位  
           virgin_crash[MAP_SIZE];       // 尚未在崩溃中看到的位  
static u8* in_dir,                       // 包含测试用例的输入目录  
          *out_dir;                      // 包含测试用例的工作目录  
static u32 round_cnt;                    // 轮次计数器  
static u32 fast;                         // 快速或慢速模式  
static u32 len;                          // 输入测试用例长度  
static int sock;                         // 用于NN通信的套接字  
static int gradient_sock;                // 用于梯度服务器的套接字  
static float previous_score = 0.0;       // 先前的多维度评分  
static u32 resource_allocation = 100;    // 资源分配百分比  
static u32 num_index[15];                // 变异的索引  
static u32 retrain_interval = 20;        // 重新训练NN的间隔  
static u32 line_cnt;                     // 行计数器  
static u32 old, now;                     // 边缘覆盖率计数器  
static u32 edge_gain;                    // 轮次之间的边缘增益  
static u32 path_depth;                   // 路径深度指标  
static u32 memory_diversity;             // 内存访问多样性指标  
  
/* 有趣测试用例的优先队列 */  
typedef struct {  
    char path[PATH_MAX];  
    float score;  
} priority_queue_item;  
  
static priority_queue_item priority_queue[PRIORITY_QUEUE_SIZE];  
static u32 priority_queue_count = 0;  
  
/* 类型定义 */  
typedef unsigned char u8;  
typedef unsigned short u16;  
typedef unsigned int u32;  
typedef unsigned long long u64;  
typedef signed char s8;  
typedef signed short s16;  
typedef signed int s32;  
typedef signed long long s64;  
  
/* 函数声明 */  
static void setup_enhanced_shm(void);  
static void init_enhanced_forkserver(char** argv);  
static void enhanced_run_target(char** argv, u8* mem, u32 len, u32 timeout);  
static u8 has_new_bits(u8* virgin_map);  
static u32 count_non_255_bytes(u8* mem);  
static u32 calculate_path_depth(void);  
static u32 calculate_memory_diversity(void);  
static void multi_dimensional_feedback(int sock);  
static void adaptive_mutate(void);  
static void gen_mutate(void);  
static void gen_mutate_slow(void);  
static void structure_aware_mutate(void);  
static void write_to_testcase(void* mem, u32 len);  
static void run_and_save_if_interesting(void);  
static void enhanced_fuzz_loop(char* grad_file, int sock);  
static void start_enhanced_fuzz(int f_len);  
static void connect_to_gradient_server(void);  
static void get_real_time_gradient(void);  
static void report_effective_seed(char* seed_path);  
static void add_to_priority_queue(char* path, float score);  
static priority_queue_item get_from_priority_queue(void);  
  
/* 设置增强型共享内存用于多维覆盖率跟踪 */  
static void setup_enhanced_shm(void) {  
    u8* shm_str;  
    u8* enhanced_shm_str;  
  
    /* 创建基本SHM段用于边缘覆盖率 */  
    shm_str = (u8*)getenv("__AFL_SHM_ID");  
    if (!shm_str) {  
        u32 shm_id = shmget(IPC_PRIVATE, MAP_SIZE, IPC_CREAT | IPC_EXCL | 0600);  
        if (shm_id < 0) {  
            perror("shmget() 失败");  
            exit(EXIT_FAILURE);  
        }  
  
        trace_bits = shmat(shm_id, NULL, 0);  
        if (trace_bits == (void*)-1) {  
            perror("shmat() 失败");  
            exit(EXIT_FAILURE);  
        }  
  
        /* 将SHM ID写入环境变量供子进程使用 */  
        char shm_str_buf[24];  
        sprintf(shm_str_buf, "%d", shm_id);  
        setenv("__AFL_SHM_ID", shm_str_buf, 1);  
    } else {  
        u32 shm_id = atoi(shm_str);  
        trace_bits = shmat(shm_id, NULL, 0);  
        if (trace_bits == (void*)-1) {  
            perror("shmat() 失败");  
            exit(EXIT_FAILURE);  
        }  
    }  
  
    /* 创建增强型SHM段用于多维覆盖率 */  
    u32 enhanced_shm_id = shmget(IPC_PRIVATE, ENHANCED_MAP_SIZE, IPC_CREAT | IPC_EXCL | 0600);  
    if (enhanced_shm_id < 0) {  
        perror("增强型 shmget() 失败");  
        exit(EXIT_FAILURE);  
    }  
  
    enhanced_trace_bits = shmat(enhanced_shm_id, NULL, 0);  
    if (enhanced_trace_bits == (void*)-1) {  
        perror("增强型 shmat() 失败");  
        exit(EXIT_FAILURE);  
    }  
  
    /* 将增强型SHM ID写入环境变量供子进程使用 */  
    char enhanced_shm_str_buf[24];  
    sprintf(enhanced_shm_str_buf, "%d", enhanced_shm_id);  
    setenv("__ENHANCED_AFL_SHM_ID", enhanced_shm_str_buf, 1);  
  
    /* 初始化virgin位图 */  
    memset(virgin_bits, 255, MAP_SIZE);  
    memset(virgin_hang, 255, MAP_SIZE);  
    memset(virgin_crash, 255, MAP_SIZE);  
}  
  
/* 初始化增强型Fork服务器以实现高效执行 */  
static void init_enhanced_forkserver(char** argv) {  
    static struct itimerval it;  
    int st_pipe[2], ctl_pipe[2];  
    int status;  
    s32 rlen;  
  
    if (pipe(st_pipe) || pipe(ctl_pipe)) {  
        perror("pipe() 失败");  
        exit(EXIT_FAILURE);  
    }  
  
    forksrv_pid = fork();  
  
    if (forksrv_pid < 0) {  
        perror("fork() 失败");  
        exit(EXIT_FAILURE);  
    }  
  
    if (!forksrv_pid) {  
        /* 子进程 - fork服务器 */  
        struct rlimit r;  
  
        /* 将管道描述符复制到FORKSRV_FD和FORKSRV_FD + 1 */  
        if (dup2(ctl_pipe[0], FORKSRV_FD) < 0 ||   
            dup2(st_pipe[1], FORKSRV_FD + 1) < 0) {  
            perror("dup2() 失败");  
            exit(EXIT_FAILURE);  
        }  
  
        close(ctl_pipe[0]);  
        close(ctl_pipe[1]);  
        close(st_pipe[0]);  
        close(st_pipe[1]);  
  
        /* 设置超时控制 */  
        if (getrlimit(RLIMIT_AS, &r)) {  
            perror("getrlimit() 失败");  
            exit(EXIT_FAILURE);  
        }  
  
        r.rlim_cur = (rlim_t)MAX_FILE;  
        setrlimit(RLIMIT_AS, &r);  
  
        /* 使用AFL_FORKSRV_INIT_TMOUT执行目标 */  
        setsid();  
        setenv("AFL_FORKSRV_INIT_TMOUT", "10000", 1);  
        execv(argv[0], argv);  
  
        /* 如果我们还活着，说明出了问题 */  
        fprintf(stderr, "Fork服务器中的execv失败\n");  
        exit(EXIT_FAILURE);  
    }  
  
    /* 父进程 */  
    close(ctl_pipe[0]);  
    close(st_pipe[1]);  
  
    fsrv_ctl_fd = ctl_pipe[1];  
    fsrv_st_fd = st_pipe[0];  
  
    /* 等待fork服务器启动 */  
    it.it_value.tv_sec = ((exec_tmout * TMOUT_MULTIPLIER) / 1000);  
    it.it_value.tv_usec = ((exec_tmout * TMOUT_MULTIPLIER) % 1000) * 1000;  
  
    setitimer(ITIMER_REAL, &it, NULL);  
  
    if (read(fsrv_st_fd, &status, 4) != 4) {  
        if (stop_soon) return;  
        perror("无法从fork服务器读取状态");  
        exit(EXIT_FAILURE);  
    }  
  
    it.it_value.tv_sec = 0;  
    it.it_value.tv_usec = 0;  
  
    setitimer(ITIMER_REAL, &it, NULL);  
  
    /* 如果我们收到了四字节的"hello"消息，一切就绪 */  
    if (status == 0x4f4b4159) {  // "OKAY"  
        printf("Fork服务器已启动并准备就绪\n");  
        return;  
    }  
  
    fprintf(stderr, "Fork服务器握手失败，状态: %x\n", status);  
    exit(EXIT_FAILURE);  
}  
  
/* 计算路径深度指标 */  
static u32 calculate_path_depth(void) {  
    u32 depth = 0;  
    u32 i;  
  
    /* 计算执行路径的深度，基于边缘覆盖率的分布 */  
    for (i = 0; i < MAP_SIZE; i++) {  
        if (trace_bits[i]) {  
            depth += trace_bits[i];  
        }  
    }  
  
    return depth;  
}  
  
/* 计算内存访问多样性指标 */  
static u32 calculate_memory_diversity(void) {  
    u32 diversity = 0;  
    u32 i;  
  
    /* 使用增强型共享内存中的内存访问信息计算多样性 */  
    for (i = 0; i < MAP_SIZE; i++) {  
        if (enhanced_trace_bits[i + MAP_SIZE]) {  
            diversity++;  
        }  
    }  
  
    return diversity;  
}  
  
/* 多维度反馈机制 */  
static void multi_dimensional_feedback(int sock) {  
    /* 计算多维度指标 */  
    u32 edge_coverage = count_non_255_bytes(virgin_bits);  
    u32 path_depth = calculate_path_depth();  
    u32 memory_diversity = calculate_memory_diversity();  
      
    /* 综合评分 */  
    float score = edge_coverage * 0.6 + path_depth * 0.3 + memory_diversity * 0.1;  
      
    /* 根据评分决定反馈信息 */  
    if (score > previous_score * 1.1) {  
        /* 显著提升，使用快速模式并增加资源 */  
        send(sock, "boost", 5, 0);  
        fast = 1;  
        resource_allocation = (resource_allocation * 12) / 10;  // 增加20%  
        if (resource_allocation > 200) resource_allocation = 200;  // 上限  
        printf("加速阶段 (评分: %.2f)\n", score);  
    } else if (score > previous_score * 1.02) {  
        /* 小幅提升，使用快速模式 */  
        send(sock, "train", 5, 0);  
        fast = 1;  
        printf("快速阶段 (评分: %.2f)\n", score);  
    } else {  
        /* 停滞，使用慢速模式 */  
        send(sock, "sloww", 5, 0);  
        fast = 0;  
        printf("慢速阶段 (评分: %.2f)\n", score);  
    }  
      
    previous_score = score;  
}  
  
/* 连接到梯度服务器 */  
static void connect_to_gradient_server(void) {  
    struct sockaddr_in serv_addr;  
      
    if ((gradient_sock = socket(AF_INET, SOCK_STREAM, 0)) < 0) {  
        perror("梯度服务器套接字创建失败");  
        return;  
    }  
      
    memset(&serv_addr, '0', sizeof(serv_addr));  
    serv_addr.sin_family = AF_INET;  
    serv_addr.sin_port = htons(GRADIENT_PORT);  
      
    if (inet_pton(AF_INET, HOST, &serv_addr.sin_addr) <= 0) {  
        perror("无效地址/地址不支持");  
        return;  
    }  
      
    if (connect(gradient_sock, (struct sockaddr *)&serv_addr, sizeof(serv_addr)) < 0) {  
        perror("梯度服务器连接失败");  
        return;  
    }  
      
    printf("已连接到梯度服务器\n");  
}  
  
/* 获取实时梯度信息 */  
static void get_real_time_gradient(void) {  
    char request[32] = "GET_GRADIENT";  
    char buffer[4096];  
    ssize_t n;  
      
    /* 发送请求 */  
    send(gradient_sock, request, strlen(request), 0);  
      
    /* 接收响应 */  
    n = recv(gradient_sock, buffer, sizeof(buffer) - 1, 0);  
    if (n <= 0) {  
        perror("从梯度服务器接收数据失败");  
        return;  
    }  
      
    buffer[n] = '\0';  
      
    /* 解析梯度信息 */  
    FILE *fp = fopen("realtime_gradient_info", "w");  
    if (fp) {  
        fputs(buffer, fp);  
        fclose(fp);  
    }  
}  
  
/* 报告有效种子 */  
static void report_effective_seed(char* seed_path) {  
    char request[PATH_MAX + 32];  
    char buffer[128];  
    ssize_t n;  
      
    /* 构建请求 */  
    sprintf(request, "REPORT_EFFECTIVE|%s", seed_path);  
      
    /* 发送请求 */  
    send(gradient_sock, request, strlen(request), 0);  
      
    /* 接收响应 */  
    n = recv(gradient_sock, buffer, sizeof(buffer) - 1, 0);  
    if (n <= 0) {  
        perror("从梯度服务器接收数据失败");  
        return;  
    }  
      
    buffer[n] = '\0';  
      
    /* 检查响应 */  
    if (strcmp(buffer, "OK") != 0) {  
        fprintf(stderr, "报告有效种子失败: %s\n", buffer);  
    }  
}  
  
/* 添加到优先队列 */  
static void add_to_priority_queue(char* path, float score) {  
    if (priority_queue_count >= PRIORITY_QUEUE_SIZE) {  
        /* 如果队列已满，替换评分最低的项 */  
        int min_idx = 0;  
        float min_score = priority_queue[0].score;  
          
        for (int i = 1; i < PRIORITY_QUEUE_SIZE; i++) {  
            if (priority_queue[i].score < min_score) {  
                min_score = priority_queue[i].score;  
                min_idx = i;  
            }  
        }  
          
        if (score > min_score) {  
            strncpy(priority_queue[min_idx].path, path, PATH_MAX - 1);  
            priority_queue[min_idx].path[PATH_MAX - 1] = '\0';  
            priority_queue[min_idx].score = score;  
        }  
    } else {  
        /* 队列未满，直接添加 */  
        strncpy(priority_queue[priority_queue_count].path, path, PATH_MAX - 1);  
        priority_queue[priority_queue_count].path[PATH_MAX - 1] = '\0';  
        priority_queue[priority_queue_count].score = score;  
        priority_queue_count++;  
    }  
}  
  
/* 从优先队列获取项 */  
static priority_queue_item get_from_priority_queue(void) {  
    if (priority_queue_count == 0) {  
        /* 队列为空，返回空项 */  
        priority_queue_item empty_item;  
        memset(&empty_item, 0, sizeof(priority_queue_item));  
        return empty_item;  
    }  
      
    /* 找到评分最高的项 */  
    int max_idx = 0;  
    float max_score = priority_queue[0].score;  
      
    for (int i = 1; i < priority_queue_count; i++) {  
        if (priority_queue[i].score > max_score) {  
            max_score = priority_queue[i].score;  
            max_idx = i;  
        }  
    }  
      
    /* 获取项 */  
    priority_queue_item item = priority_queue[max_idx];  
      
    /* 移除项 */  
    priority_queue[max_idx] = priority_queue[priority_queue_count - 1];  
    priority_queue_count--;  
      
    return item;  
}  
  
/* 自适应变异策略 */  
static void adaptive_mutate(void) {  
    /* 根据边缘增益选择变异策略 */  
    if (edge_gain > 50) {  
        /* 高效率模式：快速探索 */  
        gen_mutate();  
          
        /* 添加字节交换操作 */  
        for (int i = 0; i < 100; i++) {  
            int idx1 = rand() % len;  
            int idx2 = rand() % len;  
            u8 temp = out_buf[idx1];  
            out_buf[idx1] = out_buf[idx2];  
            out_buf[idx2] = temp;  
              
            write_to_testcase(out_buf, len);  
            run_and_save_if_interesting();  
        }  
    } else if (edge_gain > 20) {  
        /* 平衡模式 */  
        gen_mutate();  
          
        /* 添加算术运算 */  
        for (int i = 0; i < 200; i++) {  
            int idx = rand() % len;  
            int op = rand() % 4; /* 加、减、乘、异或 */  
            switch (op) {  
                case 0: out_buf[idx] += (rand() % 10); break;  
                case 1: out_buf[idx] -= (rand() % 10); break;  
                case 2: out_buf[idx] *= (1 + (rand() % 3)); break;  
                case 3: out_buf[idx] ^= (1 << (rand() % 8)); break;  
            }  
              
            write_to_testcase(out_buf, len);  
            run_and_save_if_interesting();  
        }  
    } else {  
        /* 深度探索模式 */  
        gen_mutate_slow();  
        structure_aware_mutate();  
    }  
}  
  
/* 结构感知变异 */  
static void structure_aware_mutate(void) {  
    /* 实现基于输入格式的结构感知变异 */  
 /* 实现基于输入格式的结构感知变异 */  
    int i, j, idx;  
    u8 *new_buf;  
      
    /* 尝试识别常见的文件格式结构 */  
    if (len < 8) return; // 太短，无法进行结构分析  
      
    /* 检查是否为PNG格式 */  
    if (out_buf[0] == 0x89 && out_buf[1] == 'P' && out_buf[2] == 'N' && out_buf[3] == 'G') {  
        /* PNG格式变异 - 修改块内容但保持CRC有效 */  
        for (i = 8; i < len - 12; i++) {  
            if (i + 8 < len) {  
                u32 chunk_len = (out_buf[i] << 24) | (out_buf[i+1] << 16) |   
                                (out_buf[i+2] << 8) | out_buf[i+3];  
                  
                if (chunk_len > 0 && chunk_len < 10000 && i + chunk_len + 12 < len) {  
                    /* 找到有效的PNG块，修改其数据部分 */  
                    for (j = 0; j < 10; j++) {  
                        idx = i + 8 + (rand() % chunk_len);  
                        out_buf[idx] ^= (1 + (rand() % 255));  
                          
                        write_to_testcase(out_buf, len);  
                        run_and_save_if_interesting();  
                          
                        /* 恢复原始值 */  
                        out_buf[idx] ^= (1 + (rand() % 255));  
                    }  
                }  
            }  
        }  
    }  
      
    /* 检查是否为XML/HTML格式 */  
    if ((out_buf[0] == '<' && out_buf[1] != '!') ||   
        (len > 5 && out_buf[0] == '<' && out_buf[1] == '!' &&   
         out_buf[2] == 'D' && out_buf[3] == 'O' && out_buf[4] == 'C')) {  
          
        /* XML/HTML格式变异 - 修改标签属性但保持结构完整 */  
        for (i = 0; i < len - 8; i++) {  
            if (out_buf[i] == '<' && out_buf[i+1] != '/' && out_buf[i+1] != '!') {  
                /* 找到开始标签 */  
                for (j = i + 2; j < len - 1; j++) {  
                    if (out_buf[j] == '>') {  
                        /* 找到标签结束位置 */  
                        int tag_len = j - i - 1;  
                        if (tag_len > 3) {  
                            /* 在标签内部添加或修改属性 */  
                            new_buf = malloc(len + 12);  
                            if (!new_buf) continue;  
                              
                            memcpy(new_buf, out_buf, i + tag_len);  
                            memcpy(new_buf + i + tag_len, " id=\"x\"", 7);  
                            memcpy(new_buf + i + tag_len + 7, out_buf + i + tag_len, len - i - tag_len);  
                              
                            write_to_testcase(new_buf, len + 7);  
                            run_and_save_if_interesting();  
                              
                            free(new_buf);  
                        }  
                        break;  
                    }  
                }  
            }  
        }  
    }  
      
    /* 检查是否为JSON格式 */  
    if (out_buf[0] == '{' || out_buf[0] == '[') {  
        /* JSON格式变异 - 修改值但保持结构完整 */  
        for (i = 0; i < len - 2; i++) {  
            if (out_buf[i] == '"' && i > 0 && out_buf[i-1] != '\\') {  
                /* 找到字符串开始 */  
                for (j = i + 1; j < len; j++) {  
                    if (out_buf[j] == '"' && out_buf[j-1] != '\\') {  
                        /* 找到字符串结束 */  
                        int str_len = j - i - 1;  
                        if (str_len > 0 && str_len < 100) {  
                            /* 修改字符串内容 */  
                            for (int k = 0; k < 5; k++) {  
                                idx = i + 1 + (rand() % str_len);  
                                u8 old_val = out_buf[idx];  
                                out_buf[idx] = 'A' + (rand() % 26);  
                                  
                                write_to_testcase(out_buf, len);  
                                run_and_save_if_interesting();  
                                  
                                /* 恢复原始值 */  
                                out_buf[idx] = old_val;  
                            }  
                        }  
                        break;  
                    }  
                }  
            }  
        }  
    }  
}  
  
/* 增强型运行目标程序 */  
static void enhanced_run_target(char** argv, u8* mem, u32 len, u32 timeout) {  
    static struct itimerval it;  
    static u32 prev_timed_out = 0;  
    int status = 0;  
      
    /* 清空共享内存 */  
    memset(trace_bits, 0, MAP_SIZE);  
    memset(enhanced_trace_bits, 0, ENHANCED_MAP_SIZE);  
      
    /* 设置内存屏障，确保共享内存被正确清空 */  
    __sync_synchronize();  
      
    /* 通知fork服务器执行新的测试用例 */  
    if (write(fsrv_ctl_fd, &prev_timed_out, 4) != 4) {  
        if (stop_soon) return;  
        fprintf(stderr, "无法向fork服务器请求新进程\n");  
        exit(EXIT_FAILURE);  
    }  
      
    /* 读取子进程PID */  
    if (read(fsrv_st_fd, &child_pid, 4) != 4) {  
        if (stop_soon) return;  
        fprintf(stderr, "无法从fork服务器获取PID\n");  
        exit(EXIT_FAILURE);  
    }  
      
    if (child_pid <= 0) {  
        fprintf(stderr, "Fork服务器行为异常\n");  
        exit(EXIT_FAILURE);  
    }  
      
    /* 设置超时 */  
    it.it_value.tv_sec = (timeout / 1000);  
    it.it_value.tv_usec = (timeout % 1000) * 1000;  
    setitimer(ITIMER_REAL, &it, NULL);  
      
    /* 等待子进程执行完毕 */  
    if (read(fsrv_st_fd, &status, 4) != 4) {  
        if (stop_soon) return;  
        fprintf(stderr, "无法从fork服务器获取状态\n");  
        exit(EXIT_FAILURE);  
    }  
      
    /* 取消超时 */  
    it.it_value.tv_sec = 0;  
    it.it_value.tv_usec = 0;  
    setitimer(ITIMER_REAL, &it, NULL);  
      
    /* 更新执行计数 */  
    total_execs++;  
      
    /* 计算路径深度和内存多样性 */  
    path_depth = calculate_path_depth();  
    memory_diversity = calculate_memory_diversity();  
      
    /* 设置内存屏障，确保共享内存被正确读取 */  
    __sync_synchronize();  
      
    /* 处理执行结果 */  
    prev_timed_out = child_timed_out;  
      
    if (WIFSIGNALED(status)) {  
        kill_signal = WTERMSIG(status);  
          
        if (child_timed_out && kill_signal == SIGKILL) {  
            return FAULT_TMOUT;  
        }  
          
        return FAULT_CRASH;  
    }  
      
    return FAULT_NONE;  
}  
  
/* 写入测试用例并检查是否有趣 */  
static void run_and_save_if_interesting(void) {  
    int fault = enhanced_run_target(argv, out_buf, len, exec_tmout);  
      
    if (fault != FAULT_NONE) {  
        if (fault == FAULT_CRASH) {  
            /* 保存崩溃样本 */  
            char* crash_fn = alloc_printf("%s/crash_%d_%06d", "./crashes", round_cnt, crash_cnt);  
            int crash_fd = open(crash_fn, O_WRONLY | O_CREAT | O_EXCL, 0600);  
            if (crash_fd >= 0) {  
                write(crash_fd, out_buf, len);  
                close(crash_fd);  
                crash_cnt++;  
            }  
            free(crash_fn);  
        } else if (fault == FAULT_TMOUT) {  
            /* 保存超时样本 */  
            char* tmout_fn = alloc_printf("%s/timeout_%d_%06d", "./timeouts", round_cnt, tmout_cnt);  
            int tmout_fd = open(tmout_fn, O_WRONLY | O_CREAT | O_EXCL, 0600);  
            if (tmout_fd >= 0) {  
                write(tmout_fd, out_buf, len);  
                close(tmout_fd);  
                tmout_cnt++;  
            }  
            free(tmout_fn);  
        }  
        return;  
    }  
      
    /* 检查是否发现新的覆盖率 */  
    int ret = has_new_bits(virgin_bits);  
    if (ret) {  
        /* 保存有趣的样本 */  
        char* fn;  
        if (ret == 2) {  
            fn = alloc_printf("%s/id_%d_%06d_cov", out_dir, round_cnt, mut_cnt);  
        } else {  
            fn = alloc_printf("%s/id_%d_%06d", out_dir, round_cnt, mut_cnt);  
        }  
          
        int fd = open(fn, O_WRONLY | O_CREAT | O_EXCL, 0600);  
        if (fd >= 0) {  
            write(fd, out_buf, len);  
            close(fd);  
              
            /* 报告有效种子 */  
            report_effective_seed(fn);  
              
            /* 添加到优先队列 */  
            float score = path_depth * 0.3 + memory_diversity * 0.1 + (ret == 2 ? 10.0 : 1.0);  
            add_to_priority_queue(fn, score);  
              
            mut_cnt++;  
        }  
        free(fn);  
    }  
}  
  
/* 增强型模糊测试循环 */  
static void enhanced_fuzz_loop(char* grad_file, int sock) {  
    /* 处理拼接种子 */  
    dry_run("./splice_seeds/", 1);  
      
    /* 复制梯度信息 */  
    copy_file("gradient_info_p", grad_file);  
      
    /* 打开梯度文件 */  
    FILE *stream = fopen(grad_file, "r");  
    if (!stream) {  
        perror("无法打开梯度文件");  
        exit(EXIT_FAILURE);  
    }  
      
    char *line = NULL;  
    size_t llen = 0;  
    ssize_t nread;  
    line_cnt = 0;  
      
    /* 设置重新训练间隔 */  
    int retrain_interval = 1000;  
    if (round_cnt == 0) {  
        retrain_interval = 750;  
    }  
      
    /* 主模糊测试循环 */  
    while ((nread = getline(&line, &llen, stream)) != -1) {  
        line_cnt++;  
          
        /* 检查是否需要重新训练 */  
        if (line_cnt == retrain_interval) {  
            round_cnt++;  
            now = count_non_255_bytes(virgin_bits);  
            edge_gain = now - old;  
            old = now;  
              
            /* 多维度反馈 */  
            multi_dimensional_feedback(sock);  
        }  
          
        /* 解析梯度信息 */  
        char* loc_str = strtok(line, "|");  
        char* sign_str = strtok(NULL, "|");  
        char* fn = strtok(strtok(NULL, "|"), "\n");  
          
        parse_array(loc_str, loc);  
        parse_array(sign_str, sign);  
          
        /* 每10个文件打印一次覆盖率 */  
        if ((line_cnt % 10) == 0) {  
            printf("模糊测试 %s 行计数 %d\n", fn, line_cnt);  
            printf("边缘数量 %d\n", count_non_255_bytes(virgin_bits));  
            printf("路径深度 %d\n", path_depth);  
            printf("内存多样性 %d\n", memory_diversity);  
            fflush(stdout);  
        }  
          
        /* 读取种子到内存 */  
        int fn_fd = open(fn, O_RDONLY);  
        if (fn_fd == -1) {  
            perror("打开失败");  
            continue;  
        }  
          
        struct stat st;  
        fstat(fn_fd, &st);  
        int file_len = st.st_size;  
          
        /* 清空缓冲区 */  
        memset(out_buf, 0, len);  
        memset(out_buf1, 0, len);  
        memset(out_buf2, 0, len);  
        memset(out_buf3, 0, 20000);  
          
        /* 读取种子 */  
        read(fn_fd, out_buf, file_len);  
        close(fn_fd);  
          
        /* 生成变异 */  
        adaptive_mutate();  
          
        /* 每100个测试用例获取一次实时梯度 */  
        if ((line_cnt % 100) == 0) {  
            get_real_time_gradient();  
        }  
    }  
      
    /* 清理 */  
    free(line);  
    fclose(stream);  
}  
  
/* 启动增强型模糊测试 */  
static void start_enhanced_fuzz(int f_len) {  
    /* 连接到神经网络模块 */  
    struct sockaddr_in serv_addr;  
      
    if ((sock = socket(AF_INET, SOCK_STREAM, 0)) < 0) {  
        perror("套接字创建失败");  
        exit(EXIT_FAILURE);  
    }  
      
    memset(&serv_addr, '0', sizeof(serv_addr));  
    serv_addr.sin_family = AF_INET;  
    serv_addr.sin_port = htons(PORT);  
      
    if (inet_pton(AF_INET, HOST, &serv_addr.sin_addr) <= 0) {  
        perror("无效地址/地址不支持");  
        exit(EXIT_FAILURE);  
    }  
      
    if (connect(sock, (struct sockaddr *)&serv_addr, sizeof(serv_addr)) < 0) {  
        perror("连接失败");  
        exit(EXIT_FAILURE);  
    }  
      
    /* 连接到梯度服务器 */  
    connect_to_gradient_server();  
      
    /* 设置缓冲区 */  
    out_buf = malloc(MAX_FILE);  
    if (!out_buf) {  
        perror("malloc失败");  
        exit(EXIT_FAILURE);  
    }  
      
    out_buf1 = malloc(MAX_FILE);  
    if (!out_buf1) {  
        perror("malloc失败");  
        exit(EXIT_FAILURE);  
    }  
      
    out_buf2 = malloc(MAX_FILE);  
    if (!out_buf2) {  
        perror("malloc失败");  
        exit(EXIT_FAILURE);  
    }  
      
    out_buf3 = malloc(MAX_FILE * 2);  
    if (!out_buf3) {  
        perror("malloc失败");  
        exit(EXIT_FAILURE);  
    }  
      
    len = f_len;  
      
    /* 运行初始种子 */  
    dry_run(out_dir, 2);  
      
    /* 开始模糊测试循环 */  
    char buf[16];  
    while (1) {  
        if (read(sock, buf, 5) == -1) {  
            perror("接收失败");  
            break;  
        }  
          
        enhanced_fuzz_loop("gradient_info", sock);  
        printf("接收到消息\n");  
    }  
}  
  
/* 写入测试用例 */  
static void write_to_testcase(void* mem, u32 mem_len) {  
    s32 fd;  
  
    if (out_file) {  
        unlink(out_file);  
        fd = open(out_file, O_WRONLY | O_CREAT | O_EXCL, 0600);  
    } else {  
        fd = out_fd;  
        lseek(fd, 0, SEEK_SET);  
    }  
  
    if (fd < 0) {  
        perror("无法创建文件");  
        exit(EXIT_FAILURE);  
    }  
  
    ck_write(fd, mem, mem_len, out_file);  
  
    if (!out_file) {  
        if (ftruncate(fd, mem_len)) {  
            perror("ftruncate() 失败");  
            exit(EXIT_FAILURE);  
        }  
        lseek(fd, 0, SEEK_SET);  
    } else {  
        close(fd);  
    }  
}  
  
/* 解析数组字符串 */  
static void parse_array(char* str, int* arr) {  
    char* token;  
    int i = 0;  
      
    /* 移除 '[' 和 ']' */  
    str++;  
    str[strlen(str) - 1] = '\0';  
      
    /* 解析数字 */  
    token = strtok(str, ", ");  
    while (token != NULL && i < 10000) {  
        arr[i++] = atoi(token);  
        token = strtok(NULL, ", ");  
    }  
}  
  
/* 检查是否有新的位 */  
static u8 has_new_bits(u8* virgin_map) {  
    u8* current = trace_bits;  
    u8* virgin = virgin_map;  
    u32 i;  
    u8 ret = 0;  
      
    for (i = 0; i < MAP_SIZE; i++) {  
        if (current[i] && (current[i] & virgin[i])) {  
            if (ret < 2) {  
                u8 v = virgin[i] & current[i];  
                  
                if (v == 0xff) ret = 2;  
                else ret = 1;  
            }  
              
            virgin[i] &= ~current[i];  
        }  
    }  
      
    return ret;  
}  
  
/* 计算非255字节的数量 */  
static u32 count_non_255_bytes(u8* mem) {  
    u32 i;  
    u32 ret = 0;  
      
    for (i = 0; i < MAP_SIZE; i++) {  
        if (mem[i] != 255) ret++;  
    }  
      
    return ret;  
}  
  
/* 选择块长度 */  
static u32 choose_block_len(u32 limit) {  
    u32 min_value, max_value;  
    u32 rlim = MIN(limit, HAVOC_BLK_LARGE);  
      
    switch (rand() % 3) {  
        case 0: min_value = 1; max_value = HAVOC_BLK_SMALL; break;  
        case 1: min_value = HAVOC_BLK_SMALL; max_value = HAVOC_BLK_MEDIUM; break;  
        default: min_value = HAVOC_BLK_MEDIUM; max_value = HAVOC_BLK_LARGE; break;  
    }  
      
    if (min_value >= limit) min_value = 1;  
    if (max_value >= limit) max_value = limit;  
      
    return min_value + rand() % (max_value - min_value + 1);  
}  
  
/* 复制文件 */  
static void copy_file(char* src, char* dst) {  
    FILE* in_file = fopen(src, "rb");  
    if (!in_file) {  
        perror("无法打开源文件");  
        return;  
    }  
      
    FILE* out_file = fopen(dst, "wb");  
    if (!out_file) {  
        perror("无法创建目标文件");  
        fclose(in_file);  
        return;  
    }  
      
    char buffer[4096];  
    size_t bytes;  
      
    while ((bytes = fread(buffer, 1, sizeof(buffer), in_file)) > 0) {  
        fwrite(buffer, 1, bytes, out_file);  
    }  
      
    fclose(in_file);  
    fclose(out_file);  
}  
  
/* 复制种子 */  
static void copy_seeds(char* in_dir, char* out_dir) {  
    struct dirent* de;  
    DIR* dp;  
      
    if ((dp = opendir(in_dir)) == NULL) {  
        fprintf(stderr, "无法打开目录: %s\n", in_dir);  
        return;  
    }  
      
    char src[PATH_MAX], dst[PATH_MAX];  
      
    while ((de = readdir(dp)) != NULL) {  
        if (strcmp(".", de->d_name) == 0 || strcmp("..", de->d_name) == 0) {  
            continue;  
        }  
          
        snprintf(src, PATH_MAX, "%s/%s", in_dir, de->d_name);  
        snprintf(dst, PATH_MAX, "%s/%s", out_dir, de->d_name);  
          
        copy_file(src, dst);  
    }  
      
    closedir(dp);  
}  
  
/* 主函数 */  
int main(int argc, char** argv) {  
    int opt;  
      
    /* 解析命令行参数 */  
    while ((opt = getopt(argc, argv, "+i:o:l:")) > 0) {  
        switch (opt) {  
            case 'i': /* 输入目录 */  
                if (in_dir) {  
                    fprintf(stderr, "不支持多个 -i 选项\n");  
                    exit(EXIT_FAILURE);  
                }  
                in_dir = optarg;  
                break;  
                  
            case 'o': /* 输出目录 */  
                if (out_dir) {  
                    fprintf(stderr, "不支持多个 -o 选项\n");  
                    exit(EXIT_FAILURE);  
                }  
                out_dir = optarg;  
                break;  
                  
            case 'l': /* 文件长度 */  
                sscanf(optarg, "%u", &len);  
                  
                /* 根据文件长度调整 num_index 和 havoc_blk_* */  
                if (len > 7000) {  
                    num_index[13] = (len - 1);  
                    havoc_blk_large = (len - 1);  
                } else if (len > 4000) {  
                    num_index[13] = (len - 1);  
                    num_index[12] = 3072;  
                    havoc_blk_large = (len - 1);  
                    havoc_blk_medium = 2048;  
                    havoc_blk_small = 1024;  
                }  
                  
                printf("num_index %d %d small %d medium %d large %d\n",   
                       num_index[12], num_index[13],   
                       havoc_blk_small, havoc_blk_medium, havoc_blk_large);  
                         
                printf("变异长度: %u\n", len);  
                break;  
                  
            default:  
                fprintf(stderr, "用法: %s -i <输入目录> -o <输出目录> -l <文件长度> [目标程序] [参数...]\n", argv[0]);  
                exit(EXIT_FAILURE);  
        }  
    }  
      
    /* 检查必要的参数 */  
    if (!in_dir || !out_dir || !len || optind >= argc) {  
        fprintf(stderr, "用法: %s -i <输入目录> -o <输出目录> -l <文件长度> [目标程序] [参数...]\n", argv[0]);  
        exit(EXIT_FAILURE);  
    }  
      
    /* 设置信号处理程序 */  
    setup_signal_handlers();  
      
    /* 检查CPU调度器 */  
    check_cpu_governor();  
      
    /* 获取CPU核心数 */  
    get_core_count();  
      
    /* 绑定到空闲CPU */  
    bind_to_free_cpu();  
      
    /* 设置共享内存 */  
    setup_enhanced_shm();  
      
    /* 初始化计数类 */  
    init_count_class16();  
      
    /* 设置目录和文件描述符 */  
    setup_dirs_fds();  
      
    /* 设置标准输入/输出文件 */  
    if (!out_file) setup_stdio_file();  
      
    /* 检测文件参数 */  
    detect_file_args(argv + optind + 1);  
      
    /* 设置目标路径 */  
    setup_targetpath(argv[optind]);  
      
    /* 复制种子 */  
    copy_seeds(in_dir, out_dir);  
      
    /* 初始化Fork服务器 */  
    init_enhanced_forkserver(argv + optind);  
      
    /* 开始模糊测试 */  
    start_enhanced_fuzz(len);  
      
    /* 打印结果 */  
    printf("总执行次数 %llu 边缘覆盖率 %u.\n",   
           total_execs, count_non_255_bytes(virgin_bits));  
      
    return 0;  
}
