# GitBook to PDF 转换工具

这是一个 Python 工具，用于将 GitBook 网站内容（包括图片）抓取下来，并合并生成一个单独的 PDF 文件，同时尽量保持原有的目录结构。

## 功能特点

- 抓取 GitBook 网站的完整内容
- 下载并嵌入所有图片
- 保持原有的目录结构
- 生成单一的 PDF 文件
- 自定义请求延迟，避免对服务器造成过大压力
- **多线程并行下载**，大幅提高抓取速度
- **代理服务器支持**，解决网络访问限制问题
- 智能处理标题重复问题

## 安装

1. 确保已安装 Python 3.6+
2. 克隆或下载此仓库
3. 安装依赖：

```bash
pip install -r requirements.txt
```

## 使用方法

基本用法：

```bash
python main.py https://example.gitbook.io/project/ -o output.pdf
```

### 命令行参数

- `url`: GitBook 网站的 URL（必需）
- `-o, --output`: 输出 PDF 文件路径（默认：gitbook.pdf）
- `-d, --delay`: 请求之间的延迟秒数（默认：1.0）
- `-t, --temp`: 临时文件目录（默认：自动创建）
- `-w, --workers`: 并发下载线程数（默认：3）
- `-v, --verbose`: 显示详细日志
- `-k, --keep-temp`: 保留临时文件，用于调试问题
- `-p, --proxy`: 代理服务器设置（格式：http://proxy_ip:proxy_port）

### 调试指南

如果在生成 PDF 时遇到问题，可以按照以下步骤进行调试：

1. 使用 `-v` 参数查看详细日志：

```bash
python main.py https://example.gitbook.io/project/ -v
```

2. 使用 `-k` 参数保留临时文件以便检查：

```bash
python main.py https://example.gitbook.io/project/ -k
```

3. 如果 PDF 生成失败，程序会自动保留临时文件并显示位置，您可以：

   - 检查生成的 HTML 文件是否正确
   - 查看下载的图片是否完整
   - 确认文件权限是否正确

4. 常见问题解决：
   - 如果出现字体相关错误，请确保系统安装了基本的字体
   - 如果出现网络错误，可以尝试增加 `-d` 参数的值
   - 如果页面需要登录，当前版本可能无法正确抓取内容
   - 如果生成的 PDF 有格式问题，可以检查临时目录中的 HTML 文件

### 示例

```bash
# 基本用法
python main.py https://example.gitbook.io/project/

# 指定输出文件
python main.py https://example.gitbook.io/project/ -o my_book.pdf

# 增加请求延迟（对于大型网站）
python main.py https://example.gitbook.io/project/ -d 2.5

# 保留临时文件
python main.py https://example.gitbook.io/project/ -t ./temp_files

# 显示详细日志
python main.py https://example.gitbook.io/project/ -v

# 使用代理服务器
python main.py https://example.gitbook.io/project/ -p http://127.0.0.1:8080

# 使用8个线程并行下载（加快下载速度）
python main.py https://example.gitbook.io/project/ -w 8

# 组合使用多个参数
python main.py https://example.gitbook.io/project/ -o book.pdf -d 1.5 -w 5 -p http://proxy.example.com:3128 -v
```

## 注意事项

- 请尊重网站的版权和使用条款
- 不要过于频繁地请求同一网站，可以适当增加延迟参数
- 某些 GitBook 网站可能需要登录才能访问，目前本工具不支持登录功能
- 使用多线程下载可以显著提高抓取速度（默认 3 个线程）
- 如果遇到网络访问限制，可以使用代理服务器参数 `-p` 来解决
- 使用代理时请确保：
  - 代理服务器稳定可用
  - 代理服务器支持 HTTPS（如果访问 HTTPS 网站）
  - 代理服务器响应速度良好
- 多线程下载注意事项：
  - 默认使用 3 个线程（可通过 -w 参数调整）
  - 建议线程数设置：
    - 小型网站（<50 页）：3-5 个线程
    - 中型网站（50-200 页）：5-7 个线程
    - 大型网站（>200 页）：7-10 个线程
  - 线程数过多可能导致：
    - 被目标网站限制访问
    - 本地资源占用过高
  - 可以配合延迟参数(-d)一起使用：
    - 高线程数(8+)建议配合较高延迟(1.5-3 秒)
    - 低线程数(3-5)可使用较低延迟(0.5-1 秒)
  - 如果遇到连接问题，尝试：
    - 减少线程数
    - 增加延迟时间
    - 使用代理服务器

## 许可证

MIT
