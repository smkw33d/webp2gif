import sys
import os
import subprocess
import time
import logging
import traceback
import magic
from datetime import datetime
from PyQt6.QtWidgets import (QApplication, QMainWindow, QPushButton, QProgressBar,
                          QVBoxLayout, QHBoxLayout, QWidget, QLabel, QFileDialog,
                          QMessageBox, QTextEdit, QCheckBox)
from PyQt6.QtCore import Qt, QMimeData, QThread, pyqtSignal, QSize
from PyQt6.QtGui import QDragEnterEvent, QDropEvent, QIcon
from PIL import Image
import shutil
from webptools import dwebp  # 导入webptools库

# 设置日志
log_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'logs')
os.makedirs(log_dir, exist_ok=True)
log_file = os.path.join(log_dir, f'webp2gif_{datetime.now().strftime("%Y%m%d_%H%M%S")}.log')

logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(log_file, encoding='utf-8'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger('webp2gif')

class ConversionWorker(QThread):
    progress = pyqtSignal(int)
    finished = pyqtSignal()
    error = pyqtSignal(str)
    log_message = pyqtSignal(str)  # 新增日志信号

    def __init__(self, files, debug_mode=False):
        super().__init__()
        self.files = files
        self.debug_mode = debug_mode
        logger.info(f"初始化转换工作线程，文件数量: {len(files)}")
        if self.debug_mode:
            logger.debug(f"文件列表: {', '.join(files)}")

    def log(self, message, level='info'):
        """统一的日志方法"""
        if level == 'debug':
            logger.debug(message)
        elif level == 'warning':
            logger.warning(message)
        elif level == 'error':
            logger.error(message)
        else:
            logger.info(message)
            
        # 发送日志消息到UI
        if self.debug_mode or level == 'error' or level == 'warning':
            self.log_message.emit(message)

    def check_tools(self):
        """检查转换工具是否可用"""
        tools_status = {}
        
        # 检查ffmpeg
        try:
            result = subprocess.run(['ffmpeg', '-version'],
                          stdout=subprocess.PIPE,
                          stderr=subprocess.PIPE,
                          check=False)
            if result.returncode == 0:
                ffmpeg_version = result.stdout.decode('utf-8', errors='ignore').splitlines()[0]
                self.log(f"检测到ffmpeg: {ffmpeg_version}", 'info')
                tools_status['ffmpeg'] = True
            else:
                self.log("ffmpeg命令存在但返回非零退出码", 'warning')
                tools_status['ffmpeg'] = False
        except FileNotFoundError:
            self.log("未检测到ffmpeg", 'info')
            tools_status['ffmpeg'] = False
        except Exception as e:
            self.log(f"检测ffmpeg时出错: {str(e)}", 'error')
            tools_status['ffmpeg'] = False
        
        # 检查libwebp (webptools依赖)
        try:
            # 验证webptools是否可用
            self.log("检查webptools工具...", 'info')
            tools_status['webptools'] = True
        except Exception as e:
            self.log(f"检测webptools时出错: {str(e)}", 'error')
            tools_status['webptools'] = False
            
        return tools_status
    
    def run(self):
        try:
            # 检查可用工具
            tools = self.check_tools()
            has_ffmpeg = tools.get('ffmpeg', False)
            has_webptools = tools.get('webptools', False)
            
            total = len(self.files)
            success_count = 0
            failed_count = 0
            
            self.log(f"开始转换 {total} 个文件")
            
            for i, file in enumerate(self.files, 1):
                if file.lower().endswith('.webp'):
                    file_basename = os.path.basename(file)
                    self.log(f"处理文件 ({i}/{total}): {file_basename}", 'info')
                    
                    # 检查文件存在性
                    if not os.path.exists(file):
                        error_msg = f"文件不存在: {file}"
                        self.log(error_msg, 'error')
                        self.error.emit(error_msg)
                        failed_count += 1
                        continue
                        
                    # 检查文件大小
                    try:
                        file_size = os.path.getsize(file)
                        self.log(f"文件大小: {file_size} 字节", 'debug')
                        if file_size == 0:
                            error_msg = f"文件为空: {file_basename}"
                            self.log(error_msg, 'error')
                            self.error.emit(error_msg)
                            failed_count += 1
                            continue
                    except Exception as e:
                        self.log(f"获取文件大小时出错: {str(e)}", 'error')
                    
                    # 创建输出目录
                    output_dir = os.path.join(os.path.dirname(file), 'result')
                    try:
                        os.makedirs(output_dir, exist_ok=True)
                        self.log(f"创建或确认输出目录: {output_dir}", 'debug')
                    except Exception as e:
                        error_msg = f"创建输出目录失败: {str(e)}"
                        self.log(error_msg, 'error')
                        self.error.emit(error_msg)
                        failed_count += 1
                        continue
                    
                    # 转换文件
                    output_path = os.path.join(output_dir,
                                             os.path.splitext(file_basename)[0] + '.gif')
                    self.log(f"输出路径: {output_path}", 'debug')
                    
                    try:
                        # 检测文件类型
                        try:
                            mime_type = magic.from_file(file, mime=True)
                            self.log(f"检测到文件类型: {mime_type}", 'debug')
                            if 'webp' not in mime_type.lower() and 'image' not in mime_type.lower():
                                self.log(f"警告：文件 {file_basename} 可能不是真正的WebP文件 (MIME: {mime_type})", 'warning')
                        except Exception as e:
                            self.log(f"检测文件类型时出错: {str(e)}", 'warning')
                        
                        # 转换方法1：尝试使用ffmpeg进行转换（如果可用）
                        converted = False
                        if has_ffmpeg:
                            self.log(f"使用ffmpeg转换文件: {file_basename}", 'info')
                            # cmd = ['ffmpeg', '-i', file, '-vf', 'split[s0][s1];[s0]palettegen[p];[s1][p]paletteuse', '-y', output_path]
                            cmd = ['ffmpeg', '-i', file, output_path]                            
                            try:
                                self.log(f"执行命令: {' '.join(cmd)}", 'debug')
                                process = subprocess.run(cmd, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
                                stderr_output = process.stderr.decode('utf-8', errors='ignore')
                                
                                # 检查输出文件是否存在且大小大于0
                                if os.path.exists(output_path) and os.path.getsize(output_path) > 0:
                                    self.log(f"ffmpeg转换成功: {file_basename}", 'info')
                                    success_count += 1
                                    converted = True
                                else:
                                    error_msg = f"ffmpeg似乎运行成功，但没有生成有效的输出文件: {file_basename}"
                                    self.log(error_msg, 'error')
                                    self.log(f"ffmpeg错误输出: {stderr_output}", 'debug')
                            except Exception as e:
                                self.log(f"ffmpeg执行失败: {str(e)}", 'warning')
                        
                        # 转换方法2：尝试使用webptools
                        if not converted and has_webptools:
                            self.log(f"使用webptools转换文件: {file_basename}", 'info')
                            try:
                                # webptools dwebp只能转为PNG，所以我们需要先转为PNG，然后再转为GIF
                                temp_png = os.path.join(output_dir, f"temp_{os.path.splitext(file_basename)[0]}.png")
                                
                                # 使用webptools转换为PNG
                                result = dwebp(input_image=file, output_image=temp_png, option="-o", logging="-v")
                                self.log(f"webptools处理结果: {result}", 'debug')
                                
                                if os.path.exists(temp_png) and os.path.getsize(temp_png) > 0:
                                    # 使用PIL将PNG转为GIF
                                    png_img = Image.open(temp_png)
                                    png_img.save(output_path, 'GIF')
                                    
                                    # 删除临时PNG文件
                                    os.remove(temp_png)
                                    
                                    if os.path.exists(output_path) and os.path.getsize(output_path) > 0:
                                        self.log(f"webptools转换成功: {file_basename}", 'info')
                                        success_count += 1
                                        converted = True
                                    else:
                                        self.log(f"webptools转换到PNG成功，但PNG到GIF失败: {file_basename}", 'error')
                                else:
                                    self.log(f"webptools转换失败，没有生成PNG文件: {file_basename}", 'error')
                            except Exception as e:
                                error_stack = traceback.format_exc()
                                self.log(f"webptools处理出错: {str(e)}", 'error')
                                self.log(f"错误堆栈: {error_stack}", 'debug')
                        
                        # 转换方法3：如果前面的方法都失败，尝试直接使用PIL
                        if not converted:
                            self.log(f"使用PIL尝试转换文件: {file_basename}", 'info')
                            
                            try:
                                # 尝试读取文件的前几个字节进行分析
                                with open(file, 'rb') as f:
                                    file_header = f.read(12)
                                    self.log(f"文件头: {file_header.hex()}", 'debug')
                                
                                # 尝试用PIL打开
                                img = Image.open(file)
                                self.log(f"PIL成功打开文件: {file_basename}, 格式: {img.format}, 大小: {img.size}", 'debug')
                                
                                # 获取更多图像信息用于调试
                                image_info = f"模式: {img.mode}, 格式: {img.format}"
                                if hasattr(img, 'n_frames'):
                                    image_info += f", 帧数: {img.n_frames}"
                                self.log(f"图像信息: {image_info}", 'debug')
                                
                                # 检查是否为动态WebP
                                is_animated = getattr(img, "is_animated", False)
                                self.log(f"是否为动态WebP: {is_animated}", 'debug')
                                
                                if is_animated:
                                    frames = []
                                    durations = []
                                    
                                    # 获取所有帧
                                    self.log(f"开始处理动态WebP，共 {img.n_frames} 帧", 'debug')
                                    try:
                                        for frame_idx in range(img.n_frames):
                                            img.seek(frame_idx)
                                            duration = img.info.get('duration', 100)
                                            durations.append(duration)
                                            
                                            # 确保帧被正确转换
                                            frame = img.convert('RGBA')
                                            frames.append(frame.copy())
                                            
                                            self.log(f"处理第 {frame_idx+1}/{img.n_frames} 帧, 持续时间: {duration}ms", 'debug')
                                    except Exception as e:
                                        error_stack = traceback.format_exc()
                                        self.log(f"读取WebP帧时出错: {str(e)}", 'error')
                                        self.log(f"错误堆栈: {error_stack}", 'debug')
                                        self.error.emit(f"读取{file_basename}的帧时出错: {str(e)}")
                                        failed_count += 1
                                        continue
                                    
                                    # 保存为GIF
                                    if frames:
                                        self.log(f"开始保存GIF，共 {len(frames)} 帧", 'debug')
                                        try:
                                            # 转换为RGB以避免透明度问题
                                            rgb_frames = []
                                            for frame in frames:
                                                # 创建白色背景
                                                bg = Image.new("RGB", frame.size, (255, 255, 255))
                                                # 将RGBA图像粘贴到背景上
                                                bg.paste(frame, (0, 0), frame.convert('RGBA'))
                                                rgb_frames.append(bg)
                                            
                                            rgb_frames[0].save(
                                                output_path,
                                                format='GIF',
                                                save_all=True,
                                                append_images=rgb_frames[1:],
                                                duration=durations,
                                                loop=0,
                                                disposal=2,
                                                optimize=False
                                            )
                                            
                                            # 验证输出文件
                                            if os.path.exists(output_path) and os.path.getsize(output_path) > 0:
                                                self.log(f"GIF保存成功: {os.path.basename(output_path)}", 'info')
                                                success_count += 1
                                            else:
                                                error_msg = f"GIF文件写入失败，输出文件为空或不存在: {os.path.basename(output_path)}"
                                                self.log(error_msg, 'error')
                                                self.error.emit(error_msg)
                                                failed_count += 1
                                                
                                        except Exception as e:
                                            error_stack = traceback.format_exc()
                                            error_msg = f"保存GIF时出错: {str(e)}"
                                            self.log(error_msg, 'error')
                                            self.log(f"错误堆栈: {error_stack}", 'debug')
                                            self.error.emit(f"保存{file_basename}为GIF时出错: {str(e)}")
                                            failed_count += 1
                                    else:
                                        error_msg = f"无法提取帧，frames列表为空: {file_basename}"
                                        self.log(error_msg, 'error')
                                        self.error.emit(error_msg)
                                        failed_count += 1
                                else:
                                    # 处理静态WebP
                                    self.log(f"处理静态WebP: {file_basename}", 'debug')
                                    try:
                                        # 转换RGBA到RGB
                                        img_rgb = Image.new("RGB", img.size, (255, 255, 255))
                                        img_rgb.paste(img.convert('RGBA'), (0, 0), img.convert('RGBA'))
                                        
                                        img_rgb.save(output_path, 'GIF')
                                        
                                        # 验证输出文件
                                        if os.path.exists(output_path) and os.path.getsize(output_path) > 0:
                                            self.log(f"静态GIF保存成功: {os.path.basename(output_path)}", 'info')
                                            success_count += 1
                                        else:
                                            error_msg = f"静态GIF文件写入失败，输出文件为空或不存在: {os.path.basename(output_path)}"
                                            self.log(error_msg, 'error')
                                            self.error.emit(error_msg)
                                            failed_count += 1
                                            
                                    except Exception as e:
                                        error_stack = traceback.format_exc()
                                        error_msg = f"保存静态GIF时出错: {str(e)}"
                                        self.log(error_msg, 'error')
                                        self.log(f"错误堆栈: {error_stack}", 'debug')
                                        self.error.emit(f"保存静态{file_basename}为GIF时出错: {str(e)}")
                                        failed_count += 1
                            
                            except Exception as e:
                                error_stack = traceback.format_exc()
                                error_msg = f"PIL处理过程出错: {str(e)}"
                                self.log(error_msg, 'error')
                                self.log(f"错误堆栈: {error_stack}", 'debug')
                                self.error.emit(f"处理{file_basename}时出错: {str(e)}")
                                failed_count += 1
                    
                    except Exception as e:
                        error_stack = traceback.format_exc()
                        error_msg = f"转换文件 {file_basename} 时出错: {str(e)}"
                        self.log(error_msg, 'error')
                        self.log(f"错误堆栈: {error_stack}", 'debug')
                        self.error.emit(error_msg)
                        failed_count += 1
                        continue
                else:
                    self.log(f"跳过非WebP文件: {os.path.basename(file)}", 'warning')
                
                self.progress.emit(int((i / total) * 100))
            
            summary_msg = f"转换完成: 成功 {success_count}，失败 {failed_count}，总共 {total}"
            self.log(summary_msg, 'info')
            self.finished.emit()
        except Exception as e:
            error_stack = traceback.format_exc()
            error_msg = f"转换过程中发生异常: {str(e)}"
            self.log(error_msg, 'error')
            self.log(f"错误堆栈: {error_stack}", 'debug')
            self.error.emit(error_msg)

class DropArea(QLabel):
    def __init__(self):
        super().__init__()
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setText("拖拽WebP文件到这里\n或点击选择文件")
        self.setStyleSheet("""
            QLabel {
                border: 2px dashed #aaa;
                border-radius: 10px;
                padding: 20px;
                background: #f8f9fa;
                color: #495057;
                font-size: 14px;
            }
            QLabel:hover {
                background: #e9ecef;
                border-color: #6c757d;
            }
        """)
        self.setMinimumSize(400, 200)
        self.setAcceptDrops(True)

    def dragEnterEvent(self, event: QDragEnterEvent):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()

    def dropEvent(self, event: QDropEvent):
        files = [url.toLocalFile() for url in event.mimeData().urls()]
        self.parent().process_files(files)

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("WebP转GIF工具 v1.1")
        self.setStyleSheet("""
            QMainWindow {
                background: white;
            }
            QPushButton {
                background: #007bff;
                color: white;
                border: none;
                padding: 10px 20px;
                border-radius: 5px;
                font-size: 14px;
            }
            QPushButton:hover {
                background: #0056b3;
            }
            QPushButton:pressed {
                background: #004085;
            }
            QPushButton:disabled {
                background: #6c757d;
            }
            QProgressBar {
                border: none;
                border-radius: 5px;
                text-align: center;
                background: #e9ecef;
            }
            QProgressBar::chunk {
                background: #007bff;
                border-radius: 5px;
            }
            QTextEdit {
                border: 1px solid #ced4da;
                border-radius: 5px;
                background: #f8f9fa;
                font-family: monospace;
                font-size: 12px;
            }
            QCheckBox {
                color: #495057;
                font-size: 13px;
            }
        """)

        # 创建主窗口部件
        main_widget = QWidget()
        self.setCentralWidget(main_widget)

        # 创建布局
        layout = QVBoxLayout()
        main_widget.setLayout(layout)

        # 创建拖拽区域
        self.drop_area = DropArea()
        layout.addWidget(self.drop_area)

        # 创建选择文件按钮
        select_btn = QPushButton("选择文件")
        select_btn.clicked.connect(self.select_files)
        layout.addWidget(select_btn)

        # 创建进度条
        self.progress_bar = QProgressBar()
        self.progress_bar.setVisible(False)
        layout.addWidget(self.progress_bar)

        # 创建状态标签
        self.status_label = QLabel()
        self.status_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.status_label)
        
        # 创建调试模式复选框
        self.debug_checkbox = QCheckBox("调试模式（记录详细日志）")
        self.debug_checkbox.setChecked(True)  # 默认启用调试模式
        layout.addWidget(self.debug_checkbox)
        
        # 创建日志文本框
        self.log_text = QTextEdit()
        self.log_text.setReadOnly(True)
        self.log_text.setFixedHeight(150)
        self.log_text.setPlaceholderText("日志信息将显示在这里...")
        layout.addWidget(self.log_text)
        
        # 添加初始日志
        self.append_log("程序已启动，等待转换任务...")
        self.append_log(f"日志文件路径: {log_file}")

        # 设置窗口属性
        self.setFixedSize(600, 650)
        self.setWindowFlags(Qt.WindowType.WindowStaysOnTopHint)

    def append_log(self, message):
        """向日志文本框添加消息"""
        self.log_text.append(f"[{datetime.now().strftime('%H:%M:%S')}] {message}")
        # 自动滚动到底部
        self.log_text.verticalScrollBar().setValue(self.log_text.verticalScrollBar().maximum())

    def select_files(self):
        files, _ = QFileDialog.getOpenFileNames(
            self,
            "选择WebP文件",
            "",
            "WebP文件 (*.webp)"
        )
        if files:
            self.process_files(files)

    def process_files(self, files):
        # 过滤出.webp文件
        webp_files = [f for f in files if f.lower().endswith('.webp')]
        if not webp_files:
            self.status_label.setText("没有选择WebP文件！")
            self.status_label.setStyleSheet("color: #dc3545;")
            self.append_log("错误: 没有选择WebP文件")
            return

        # 开始转换
        self.progress_bar.setVisible(True)
        self.progress_bar.setValue(0)
        self.status_label.setText("正在转换...")
        self.status_label.setStyleSheet("color: #007bff;")
        self.append_log(f"开始转换 {len(webp_files)} 个文件")

        # 创建工作线程
        debug_mode = self.debug_checkbox.isChecked()
        self.worker = ConversionWorker(webp_files, debug_mode)
        self.worker.progress.connect(self.update_progress)
        self.worker.finished.connect(self.conversion_finished)
        self.worker.error.connect(self.conversion_error)
        self.worker.log_message.connect(self.append_log)
        self.worker.start()

    def update_progress(self, value):
        self.progress_bar.setValue(value)

    def conversion_finished(self):
        self.status_label.setText("转换完成！文件保存在result文件夹中")
        self.status_label.setStyleSheet("color: #28a745;")
        self.append_log("转换任务完成")

    def conversion_error(self, error_msg):
        self.status_label.setText(f"转换出错：{error_msg}")
        self.status_label.setStyleSheet("color: #dc3545;")
        self.append_log(f"错误: {error_msg}")

if __name__ == '__main__':
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec())