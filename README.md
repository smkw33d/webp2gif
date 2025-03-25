# WebP转GIF工具

一个简单易用的Windows GUI工具，可以将WebP格式（包括动态WebP）批量转换为GIF格式。

## 功能特点

- 现代化Material Design界面
- 支持拖拽上传文件
- 批量转换功能
- 实时显示转换进度
- 自动将转换后的文件保存在源图片目录下的result文件夹
- 支持静态和动态WebP格式
- 自动检测并使用ffmpeg（如果已安装）以获得更高质量的转换结果

## 使用方法

1. 双击`start.bat`启动程序
2. 将WebP文件拖入窗口，或点击"选择文件"按钮选择文件
3. 等待转换完成，查看result文件夹中的GIF文件

## 系统要求

- Windows 7/8/10/11
- Python 3.7+
- 依赖项：PyQt6, Pillow
- 推荐安装ffmpeg以获得更好的转换质量

## 安装说明

1. 确保已安装Python 3.7或更高版本
2. 运行`start.bat`文件，它会自动创建虚拟环境并安装所需依赖
3. 如果需要更高质量的GIF，建议安装ffmpeg并将其添加到系统PATH中

## 可选：安装ffmpeg

为了获得更高质量的GIF转换，建议安装ffmpeg：

1. 从[ffmpeg官网](https://ffmpeg.org/download.html)下载最新版本
2. 解压到任意位置（例如`C:\ffmpeg`）
3. 将ffmpeg的bin目录（例如`C:\ffmpeg\bin`）添加到系统环境变量PATH中

## 疑难解答

如果遇到"无法读取文件"错误：
- 确保文件格式确实是WebP
- 检查文件是否已被其他程序占用
- 尝试使用管理员权限运行程序