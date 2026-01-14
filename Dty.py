import tkinter as tk
from tkinter import messagebox, scrolledtext
import threading
import time
import pyautogui # For taking screenshots (alternative method)
from PIL import Image, ImageGrab # For taking screenshots and image processing
import pytesseract # For OCR
import requests # For sending HTTP requests to the callback URL
import json # For handling JSON data
import logging # For logging
from datetime import datetime # For timestamps
import os # For file paths
import sys # For system-specific parameters and functions
import hashlib # For simple deduplication hashing
import re # For regular expressions
from pynput import mouse # For mouse listener during region selection
import mss # Alternative screenshot library, potentially faster
import io # For BytesIO
from flask import Flask, request, jsonify # For the internal API server


# --- 配置 ---

# 设置日志配置
logging.basicConfig(
    level=logging.DEBUG,  # 设置日志级别为 DEBUG，以便捕获更多信息
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("app.log", encoding='utf-8'), # 写入文件
        logging.StreamHandler(sys.stdout) # 同时输出到控制台
    ]
)
logger = logging.getLogger(__name__)

# Tesseract OCR 可执行文件路径 (根据你的实际安装路径修改)
# Windows 示例:
# pytesseract.pytesseract.tesseract_cmd = r'C:\Program Files\Tesseract-OCR\tesseract.exe'
# macOS/Linux 示例 (如果在PATH中，可能不需要设置):
# pytesseract.pytesseract.tesseract_cmd = '/usr/local/bin/tesseract'

# --- 注意：你需要修改为你自己的 Tesseract 安装路径 ---
# --- Windows 用户尤其要注意这个路径 ---
# --- 如果不设置或设置错误，OCR 会失败 ---
pytesseract.pytesseract.tesseract_cmd = r'C:\Program Files\Tesseract-OCR\tesseract.exe'

# 默认回调URL (可以在GUI中修改)
DEFAULT_CALLBACK_URL = "http://localhost:5001/receive_payment"

# OCR语言 (中文简体+英文)
OCR_LANG = 'chi_sim+eng'

# --- GUI 类定义 ---
class NotificationWindow(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Dty 微信收款OCR监听器")
        self.geometry("550x800") # 增加高度以容纳调试功能区域

        # --- GUI元素 ---
        # 状态标签
        self.status_label = tk.Label(self, text="状态: 未运行", fg="red")
        self.status_label.pack(pady=10)

        # 区域坐标输入框
        coord_frame = tk.Frame(self)
        coord_frame.pack(pady=5)
        tk.Label(coord_frame, text="监控区域 (左,顶,宽,高):").pack(side=tk.LEFT)
        self.coord_entry = tk.Entry(coord_frame, width=30)
        self.coord_entry.insert(0, "0,0,100,100") # 默认值
        self.coord_entry.pack(side=tk.LEFT, padx=5)
        self.select_button = tk.Button(coord_frame, text="选择区域", command=self.select_region)
        self.select_button.pack(side=tk.LEFT, padx=5)

        # 回调URL输入框
        url_frame = tk.Frame(self)
        url_frame.pack(pady=5)
        tk.Label(url_frame, text="回调URL:").pack(side=tk.LEFT)
        self.url_entry = tk.Entry(url_frame, width=40)
        self.url_entry.insert(0, DEFAULT_CALLBACK_URL)
        self.url_entry.pack(side=tk.LEFT, padx=5)

        # 控制按钮
        button_frame = tk.Frame(self)
        button_frame.pack(pady=10)
        self.start_button = tk.Button(button_frame, text="开始监控", command=self.start_monitoring)
        self.start_button.pack(side=tk.LEFT, padx=10)
        self.stop_button = tk.Button(button_frame, text="停止监控", command=self.stop_monitoring, state=tk.DISABLED)
        self.stop_button.pack(side=tk.LEFT, padx=10)

        # --- 日志显示区域 ---
        log_frame = tk.Frame(self)
        log_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)
        tk.Label(log_frame, text="日志:").pack(anchor=tk.W)
        self.log_text = scrolledtext.ScrolledText(log_frame, height=10, state=tk.DISABLED)
        self.log_text.pack(fill=tk.BOTH, expand=True)

        # --- 新增：收款记录显示区域 ---
        payments_frame = tk.LabelFrame(self, text="收款记录", padx=5, pady=5)
        payments_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)

        self.payments_text = scrolledtext.ScrolledText(payments_frame, height=8, state=tk.DISABLED)
        self.payments_text.pack(fill=tk.BOTH, expand=True)
        # --- 新增代码结束 ---

        # --- 新增：调试功能区域 ---
        debug_frame = tk.LabelFrame(self, text="调试功能 - 手动发送测试数据", padx=5, pady=5)
        debug_frame.pack(fill=tk.X, padx=10, pady=5)

        # 金额输入
        amount_frame = tk.Frame(debug_frame)
        amount_frame.pack(fill=tk.X, pady=2)
        tk.Label(amount_frame, text="金额:", width=10, anchor='w').pack(side=tk.LEFT)
        self.debug_amount_entry = tk.Entry(amount_frame, width=20)
        self.debug_amount_entry.insert(0, "0.01")
        self.debug_amount_entry.pack(side=tk.LEFT, padx=5)

        # 用户备注输入
        memo_frame = tk.Frame(debug_frame)
        memo_frame.pack(fill=tk.X, pady=2)
        tk.Label(memo_frame, text="用户备注:", width=10, anchor='w').pack(side=tk.LEFT)
        self.debug_memo_entry = tk.Entry(memo_frame, width=40)
        self.debug_memo_entry.insert(0, "测试备注")
        self.debug_memo_entry.pack(side=tk.LEFT, padx=5)

        # 订单ID输入（可选）
        order_frame = tk.Frame(debug_frame)
        order_frame.pack(fill=tk.X, pady=2)
        tk.Label(order_frame, text="订单ID:", width=10, anchor='w').pack(side=tk.LEFT)
        self.debug_order_entry = tk.Entry(order_frame, width=40)
        self.debug_order_entry.insert(0, "")  # 留空则自动生成
        self.debug_order_entry.pack(side=tk.LEFT, padx=5)
        tk.Label(order_frame, text="(留空自动生成)", fg="gray").pack(side=tk.LEFT)

        # 付款方备注输入（可选）
        payer_memo_frame = tk.Frame(debug_frame)
        payer_memo_frame.pack(fill=tk.X, pady=2)
        tk.Label(payer_memo_frame, text="付款方备注:", width=10, anchor='w').pack(side=tk.LEFT)
        self.debug_payer_memo_entry = tk.Entry(payer_memo_frame, width=40)
        self.debug_payer_memo_entry.insert(0, "")  # 可选字段
        self.debug_payer_memo_entry.pack(side=tk.LEFT, padx=5)
        tk.Label(payer_memo_frame, text="(可选)", fg="gray").pack(side=tk.LEFT)

        # 发送按钮
        debug_button_frame = tk.Frame(debug_frame)
        debug_button_frame.pack(fill=tk.X, pady=5)
        self.debug_send_button = tk.Button(debug_button_frame, text="发送测试数据到API", command=self.send_debug_payment, bg="#4CAF50", fg="white")
        self.debug_send_button.pack(side=tk.LEFT, padx=5)
        self.debug_clear_button = tk.Button(debug_button_frame, text="清空输入", command=self.clear_debug_inputs)
        self.debug_clear_button.pack(side=tk.LEFT, padx=5)
        # --- 调试功能区域结束 ---

        # --- 状态变量 ---
        self.monitoring_thread = None
        self.is_monitoring = False
        self.region_selected = False
        self.selected_region = None

        # 用于简单去重的变量
        self.last_processed_hash = None

    def log_message(self, message):
        """在GUI日志区域和Python日志系统中同时记录消息"""
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        formatted_message = f"[{timestamp}] {message}"

        # 更新GUI日志
        self.log_text.config(state=tk.NORMAL)
        self.log_text.insert(tk.END, formatted_message + "\n")
        self.log_text.see(tk.END) # 自动滚动到底部
        self.log_text.config(state=tk.DISABLED)

        # 记录到Python日志
        logger.info(message)

    # --- 更新代码：增强收款记录显示，明确区分备注 ---
    def add_payment_record(self, amount, payer_memo, timestamp):
        """
        在GUI的收款记录区域添加一条新记录。
        :param amount: 金额 (字符串)
        :param payer_memo: 付款方备注/时间等信息 (字符串)
        :param timestamp: Unix时间戳 (整数)
        """
        try:
            # 将时间戳转换为可读格式
            readable_time = datetime.fromtimestamp(timestamp).strftime("%Y-%m-%d %H:%M:%S")
        except Exception as e:
            logger.warning(f"时间戳转换失败: {e}")
            readable_time = "时间解析失败"

        # --- 格式化记录字符串 ---
        # 清晰地标记出金额、时间和备注
        # 示例: [2023-10-27 10:30:00] 收到 ¥10.00 | 备注: 测试付款
        record = f"[{readable_time}] 收到 ¥{amount} | 备注: {payer_memo}"

        # 安全地更新GUI (在主线程中)
        def update_gui():
            self.payments_text.config(state=tk.NORMAL)
            self.payments_text.insert(tk.END, record + "\n")
            self.payments_text.see(tk.END) # 自动滚动到底部
            self.payments_text.config(state=tk.DISABLED)

        # 使用 after 确保线程安全
        self.after(0, update_gui)
    # --- 更新代码结束 ---

    def select_region(self):
        """启动鼠标监听以选择监控区域"""
        if self.is_monitoring:
            messagebox.showwarning("警告", "监控正在进行中，请先停止监控再选择区域。")
            return

        self.log_message("已启动鼠标监听器用于区域选择。")
        self.region_selected = False
        self.selected_region = None

        # 创建一个非阻塞的鼠标监听器
        self.mouse_listener = MouseRegionSelector(self)
        self.mouse_listener.start_listening() # 启动监听

    def start_monitoring(self):
        """启动监控线程"""
        if self.is_monitoring:
             messagebox.showinfo("信息", "监控已在运行。")
             return

        coords_str = self.coord_entry.get()
        try:
            left, top, width, height = map(int, coords_str.split(','))
            self.selected_region = {"left": left, "top": top, "width": width, "height": height}
            self.log_message(f"已选择监控区域: {self.selected_region}")

            # 获取回调URL
            callback_url = self.url_entry.get().strip()
            if not callback_url:
                 messagebox.showerror("错误", "请输入有效的回调URL。")
                 return

            # 更新UI状态
            self.start_button.config(state=tk.DISABLED)
            self.stop_button.config(state=tk.NORMAL)
            self.status_label.config(text="状态: 监控中...", fg="green")

            # 启动监控线程
            self.is_monitoring = True
            self.monitoring_thread = threading.Thread(target=self.run_monitoring_loop, args=(callback_url,), daemon=True)
            self.monitoring_thread.start()

        except ValueError:
            messagebox.showerror("错误", "区域坐标格式无效，请输入 '左,顶,宽,高' 的整数形式。")

    def stop_monitoring(self):
        """停止监控"""
        if not self.is_monitoring:
             messagebox.showinfo("信息", "监控未在运行。")
             return

        self.log_message("正在停止监控...")
        self.is_monitoring = False

        # 等待监控线程结束
        if self.monitoring_thread and self.monitoring_thread.is_alive():
            self.monitoring_thread.join(timeout=5) # 等待最多5秒

        # 更新UI状态
        self.start_button.config(state=tk.NORMAL)
        self.stop_button.config(state=tk.DISABLED)
        self.status_label.config(text="状态: 已停止", fg="red")
        self.log_message("监控已停止。")

    def run_monitoring_loop(self, callback_url):
        """核心监控循环，在独立线程中运行"""
        self.log_message("监控线程循环开始。")
        try:
            while self.is_monitoring:
                if self.selected_region:
                    try:
                        # 1. 截图指定区域 (使用 mss)
                        with mss.mss() as sct:
                            # mss 需要 monitor 参数，我们构建一个
                            monitor = {
                                "left": self.selected_region["left"],
                                "top": self.selected_region["top"],
                                "width": self.selected_region["width"],
                                "height": self.selected_region["height"]
                            }

                            # 截图
                            screenshot = sct.grab(monitor)

                            # 将 mss 截图转换为 PIL Image
                            img_buffer = io.BytesIO(mss.tools.to_png(screenshot.rgb, screenshot.size))
                            img = Image.open(img_buffer)

                        # 2. 执行OCR识别
                        # 使用 BytesIO 将图像传递给 tesseract，避免临时文件
                        custom_config = f'--oem 3 --psm 6 -l {OCR_LANG}'

                        # pytesseract.image_to_string 可以直接接受 PIL Image
                        ocr_text = pytesseract.image_to_string(img, config=custom_config)

                        logger.debug(f"OCR识别结果:\n{ocr_text}")

                        # 3. 处理OCR结果
                        # 移除OCR文本中的所有空格和换行符，以便更鲁棒地匹配关键词
                        ocr_text_no_spaces = ocr_text.replace(' ', '').replace('\n', '').replace('\r', '')
                        logger.debug(f"处理后的OCR文本 (无空格/换行): {ocr_text_no_spaces}")

                        # 假设微信通知包含 "收款成功" (即使OCR加了空格，移除后也能匹配)
                        if "收款成功" in ocr_text_no_spaces:

                            # 简单去重机制：计算当前OCR文本的哈希值
                            current_text_hash = hashlib.md5(ocr_text.strip().encode('utf-8')).hexdigest()
                            if current_text_hash == self.last_processed_hash:
                                logger.debug("检测到相同内容，可能是重复通知，跳过。")
                                time.sleep(2) # 即使跳过也短暂等待
                                continue # 跳过重复内容

                            # --- 强制调试版金额和时间提取 ---
                            logger.debug(f"[DEBUG] 开始提取金额和时间...")
                            logger.debug(f"[DEBUG] 原始OCR文本: '{repr(ocr_text)}'") # repr 显示 \n 等
                            ocr_text_normalized_for_debug = ocr_text.replace('\n', ' ').replace('\r', ' ')
                            logger.debug(f"[DEBUG] 标准化后文本 (用于提取): '{ocr_text_normalized_for_debug}'")

                            # --- 提取金额 (基于关键词定位法, 适配OCR空格) ---
                            amount = "未知"
                            try:
                                # 1. 定义两种可能的关键词形式：紧密型 和 OCR空格型
                                keywords_to_try = ["收款金额", "收 款 金 额"] # 添加带空格的版本

                                keyword_found_index = -1
                                found_keyword = ""
                                for keyword in keywords_to_try:
                                    keyword_index = ocr_text_normalized_for_debug.find(keyword)
                                    if keyword_index != -1:
                                        keyword_found_index = keyword_index
                                        found_keyword = keyword
                                        break # 找到一个就停止

                                if keyword_found_index != -1:
                                    logger.debug(f"[DEBUG] 找到关键词: '{found_keyword}'")
                                    # 2. 找到关键词后，从此位置之后截取一段文本用于搜索数字
                                    #    例如，截取关键词后 20 个字符
                                    start_search_index = keyword_found_index + len(found_keyword)
                                    text_after_keyword = ocr_text_normalized_for_debug[start_search_index : start_search_index + 20]
                                    logger.debug(f"[DEBUG] 关键词'{found_keyword}'之后的文本片段: '{text_after_keyword}'")

                                    # 3. 在截取的片段中寻找最常见的金额格式 (例如 0.01, 100.00)
                                    #    这个正则比较宽松，只找数字和小数点
                                    amount_in_fragment_match = re.search(r'(\d+(?:\.\d{2})?)', text_after_keyword)
                                    if amount_in_fragment_match:
                                        amount = amount_in_fragment_match.group(1)
                                        logger.debug(f"[DEBUG] 通过关键词定位法提取到金额: {amount}")
                                    else:
                                        logger.debug(f"[DEBUG] 在关键词后的片段中未找到标准金额格式。")
                                else:
                                    logger.debug(f"[DEBUG] 未在标准化文本中找到任何关键词 {keywords_to_try}。")
                            except Exception as e:
                                logger.error(f"[ERROR] 在基于关键词提取金额时发生异常: {e}")


                            # 如果关键词法失败，可以考虑回退到旧的符号匹配法（可选）
                            # if amount == "未知":
                            #     # ... (这里粘贴之前的符号匹配代码逻辑) ...

                            # --- 提取时间 (修复变量未定义问题) ---
                            timestamp_str = "未知时间" # <--- 关键：提前定义并初始化默认值
                            try:
                                # 定义可能的时间关键词
                                time_keywords_to_try = ["收款时间", "收 款 时 间", "到账时间", "到 账 时 间"]
                                
                                time_found = False
                                for keyword in time_keywords_to_try:
                                    keyword_index = ocr_text_normalized_for_debug.find(keyword)
                                    if keyword_index != -1:
                                        # 找到关键词，从此处往后截取一段文本
                                        start_index = keyword_index + len(keyword)
                                        # 截取接下来的 25 个字符用于时间匹配
                                        text_after_keyword = ocr_text_normalized_for_debug[start_index : start_index + 25]
                                        logger.debug(f"[DEBUG] 时间关键词'{keyword}'之后的文本片段: '{text_after_keyword}'")
                                        
                                        # 尝试匹配常见的时间格式
                                        # 格式1: 2025-12-30 18:47:40 或 2025/12/30 18:47:40
                                        time_match = re.search(r'(\d{4}[-/]\d{1,2}[-/]\d{1,2}\s*\d{1,2}:\d{2}(?::\d{2})?)', text_after_keyword)
                                        if time_match:
                                            timestamp_str = time_match.group(1).strip()
                                            time_found = True
                                            logger.debug(f"[DEBUG] 通过关键词定位法提取到时间: {timestamp_str}")
                                            break
                                        
                                        # 格式2: 18:47:40 或 18:47 (仅时间)
                                        time_match = re.search(r'(\d{1,2}:\d{2}(?::\d{2})?)', text_after_keyword)
                                        if time_match:
                                            timestamp_str = time_match.group(1).strip()
                                            time_found = True
                                            logger.debug(f"[DEBUG] 通过关键词定位法提取到时间(仅时分秒): {timestamp_str}")
                                            break
                                
                                # 如果关键词法失败，尝试在整个文本中搜索时间格式
                                if not time_found:
                                    logger.debug("[DEBUG] 未通过关键词找到时间，尝试全文搜索时间格式...")
                                    # 尝试匹配完整日期时间格式
                                    time_match = re.search(r'(\d{4}[-/]\d{1,2}[-/]\d{1,2}\s*\d{1,2}:\d{2}(?::\d{2})?)', ocr_text_normalized_for_debug)
                                    if time_match:
                                        timestamp_str = time_match.group(1).strip()
                                        logger.debug(f"[DEBUG] 全文搜索提取到时间: {timestamp_str}")
                                    else:
                                        # 尝试匹配仅时间格式
                                        time_match = re.search(r'(\d{1,2}:\d{2}:\d{2})', ocr_text_normalized_for_debug)
                                        if time_match:
                                            timestamp_str = time_match.group(1).strip()
                                            logger.debug(f"[DEBUG] 全文搜索提取到时间(仅时分秒): {timestamp_str}")
                                        else:
                                            logger.debug("[DEBUG] 未能从OCR文本中提取到时间信息。")
                            except Exception as e:
                                logger.error(f"[ERROR] 在提取时间时发生异常: {e}")

                            # --- 新增：提取用户备注 ---
                            user_memo = "无备注"
                            try:
                                # 定义可能的备注关键词 (根据微信实际显示调整)
                                memo_keywords_to_try = ["付款方备注", "转账备注", "付 款 方 备 注"]

                                # 在标准化后的文本中查找
                                normalized_ocr_for_memo = ocr_text_normalized_for_debug # 使用前面定义的变量

                                memo_found = False
                                for keyword in memo_keywords_to_try:
                                    keyword_index = normalized_ocr_for_memo.find(keyword)
                                    if keyword_index != -1:
                                        # 找到关键词，从此处往后截取一段文本
                                        start_index = keyword_index + len(keyword)
                                        # 假设备注不会太长，比如截取接下来的 30 个字符
                                        potential_memo = normalized_ocr_for_memo[start_index : start_index + 30].strip()

                                        # --- 改进：更精细地清理和截断备注 ---
                                        # 1. 去掉开头可能的冒号和空格
                                        potential_memo = potential_memo.lstrip(':').lstrip()

                                        # 2. 如果有换行，则只取第一行
                                        potential_memo = potential_memo.split('\n')[0]

                                        # 3. 【关键改进】寻找常见的终止符并截断
                                        # 定义应在备注后停止的关键词（通常是下一个信息块的开始）
                                        truncation_indicators = ["汇", "总", "备", "注"] # "汇总", "备注" 的首字

                                        # 遍历这些指示符，找到最早出现的位置
                                        earliest_trunc_pos = len(potential_memo) # 默认不截断
                                        for indicator in truncation_indicators:
                                            pos = potential_memo.find(indicator)
                                            if pos != -1 and pos < earliest_trunc_pos:
                                                earliest_trunc_pos = pos

                                        # 执行截断
                                        final_user_memo = potential_memo[:earliest_trunc_pos].strip()

                                        # 4. 确保最终结果不为空
                                        if final_user_memo:
                                            user_memo = final_user_memo
                                            memo_found = True
                                            logger.debug(f"[DEBUG] 找到用户备注关键词 '{keyword}', 提取并截断后备注: '{user_memo}'")
                                            break # 找到一个就停止
                                        # --- 改进结束 ---

                                if not memo_found:
                                    logger.debug("[DEBUG] 未在OCR文本中找到用户备注关键词。")

                            except Exception as e:
                                logger.error(f"[ERROR] 在提取用户备注时发生异常: {e}")

                            # --- 构造数据 ---
                            # 将时间和其他信息组合成 payer_memo，真正的用户备注单独存放或合并
                            # 如果 OCR 时间提取失败，使用当前系统时间作为回退
                            if timestamp_str == "未知时间":
                                current_time_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                                ocr_info_memo = f"[系统时间] {current_time_str}"
                                logger.debug(f"[DEBUG] OCR时间提取失败，使用系统时间: {current_time_str}")
                            else:
                                ocr_info_memo = f"[OCR时间] {timestamp_str}"
                            
                            if user_memo != "无备注":
                                # 可以选择只显示用户备注，或者两者都显示
                                # 方式一：只显示用户备注
                                # final_payer_memo = user_memo
                                # 方式二：合并显示 (推荐)
                                final_payer_memo = f"{ocr_info_memo} | 用户备注: {user_memo}"
                            else:
                                final_payer_memo = ocr_info_memo

                            payment_data = {
                                "order_id": f"ocr_detected_{int(time.time())}",
                                "amount": amount,
                                "payer_memo": final_payer_memo, # 使用组合后的备注
                                "timestamp": int(time.time()),
                                "ocr_raw_text": ocr_text,
                                "user_memo": user_memo # 可选：单独存一份用户备注
                            }
                            logger.debug(f"[DEBUG] 最终构造的 payment_data: {payment_data}")
                            # --- 强制调试版结束 ---


                            # 4. 发送通知到回调URL
                            try:
                                headers = {'Content-Type': 'application/json'}
                                response = requests.post(callback_url, data=json.dumps(payment_data), headers=headers, timeout=10)
                                if response.status_code == 200:
                                    logger.info(f"成功发送通知到 {callback_url}。响应: {response.status_code}")
                                    # 更新去重哈希
                                    self.last_processed_hash = current_text_hash

                                    # --- 新增代码开始：成功发送后更新GUI收款记录 ---
                                    # 确保 payment_data 中包含所需字段
                                    if 'amount' in payment_data and 'payer_memo' in payment_data and 'timestamp' in payment_data:
                                        self.add_payment_record(
                                            payment_data['amount'],
                                            payment_data['payer_memo'],
                                            payment_data['timestamp']
                                        )
                                    else:
                                        logger.warning("payment_data 缺少必要字段，无法添加到GUI收款记录。")
                                    # --- 新增代码结束 ---

                                else:
                                    logger.error(f"发送通知失败。状态码: {response.status_code}, 响应: {response.text}")
                            except requests.exceptions.RequestException as e:
                                logger.error(f"发送请求时发生网络错误: {e}")

                    except Exception as e:
                         logger.error(f"监控循环中发生错误: {e}", exc_info=True) # exc_info=True 打印堆栈跟踪

                time.sleep(2) # 每2秒检查一次

        except Exception as e:
             logger.critical(f"监控线程发生未处理的异常: {e}", exc_info=True)
        finally:
            self.is_monitoring = False # 确保标志位被清除
            logger.info("监控线程循环结束。")
            # 通知主线程更新GUI (通过事件队列安全地调用)
            self.after(0, self._on_monitoring_stopped_in_main_thread)

    def _on_monitoring_stopped_in_main_thread(self):
         """在主线程中安全地更新GUI状态"""
         if not self.is_monitoring: # 再次确认，以防竞态条件
              self.start_button.config(state=tk.NORMAL)
              self.stop_button.config(state=tk.DISABLED)
              self.status_label.config(text="状态: 已停止", fg="red")
              self.log_message("主线程已处理监控停止事件并更新GUI。")

    # --- 新增：调试功能方法 ---
    def send_debug_payment(self):
        """发送调试/测试支付数据到API"""
        # 获取输入值
        amount = self.debug_amount_entry.get().strip()
        user_memo = self.debug_memo_entry.get().strip()
        order_id = self.debug_order_entry.get().strip()
        payer_memo = self.debug_payer_memo_entry.get().strip()
        
        # 验证金额
        if not amount:
            messagebox.showerror("错误", "请输入金额")
            return
        
        try:
            amount_float = float(amount)
            if amount_float <= 0:
                messagebox.showerror("错误", "金额必须大于0")
                return
            # 格式化金额为两位小数
            amount = f"{amount_float:.2f}"
        except ValueError:
            messagebox.showerror("错误", "请输入有效的金额数字")
            return
        
        # 自动生成订单ID（如果未提供）
        if not order_id:
            order_id = f"debug_test_{int(time.time())}"
        
        # 构建付款方备注
        current_time_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        if payer_memo:
            final_payer_memo = f"[调试] {current_time_str} | {payer_memo}"
        else:
            final_payer_memo = f"[调试] {current_time_str}"
        
        if user_memo:
            final_payer_memo += f" | 用户备注: {user_memo}"
        
        # 构造测试数据
        payment_data = {
            "order_id": order_id,
            "amount": amount,
            "payer_memo": final_payer_memo,
            "timestamp": int(time.time()),
            "ocr_raw_text": "[调试模式] 手动发送的测试数据",
            "user_memo": user_memo if user_memo else "无备注"
        }
        
        # 获取回调URL
        callback_url = self.url_entry.get().strip()
        if not callback_url:
            messagebox.showerror("错误", "请输入有效的回调URL")
            return
        
        self.log_message(f"[调试] 正在发送测试数据: 金额={amount}, 备注={user_memo}")
        
        # 在后台线程中发送请求，避免阻塞GUI
        def send_request():
            try:
                headers = {'Content-Type': 'application/json'}
                response = requests.post(callback_url, data=json.dumps(payment_data), headers=headers, timeout=10)
                
                if response.status_code == 200:
                    self.after(0, lambda: self.log_message(f"[调试] 测试数据发送成功! 响应: {response.status_code}"))
                    # 更新GUI收款记录
                    self.after(0, lambda: self.add_payment_record(
                        payment_data['amount'],
                        payment_data['payer_memo'],
                        payment_data['timestamp']
                    ))
                    self.after(0, lambda: messagebox.showinfo("成功", f"测试数据发送成功!\n\n订单ID: {order_id}\n金额: ¥{amount}\n备注: {user_memo}"))
                else:
                    self.after(0, lambda: self.log_message(f"[调试] 发送失败! 状态码: {response.status_code}, 响应: {response.text}"))
                    self.after(0, lambda: messagebox.showerror("失败", f"发送失败!\n状态码: {response.status_code}\n响应: {response.text}"))
            except requests.exceptions.ConnectionError:
                self.after(0, lambda: self.log_message(f"[调试] 连接失败! 请确保API服务器正在运行"))
                self.after(0, lambda: messagebox.showerror("连接失败", f"无法连接到 {callback_url}\n请确保API服务器正在运行"))
            except requests.exceptions.Timeout:
                self.after(0, lambda: self.log_message(f"[调试] 请求超时!"))
                self.after(0, lambda: messagebox.showerror("超时", "请求超时，请检查网络连接"))
            except Exception as e:
                self.after(0, lambda: self.log_message(f"[调试] 发送时发生错误: {e}"))
                self.after(0, lambda: messagebox.showerror("错误", f"发送时发生错误:\n{e}"))
        
        # 启动后台线程发送请求
        threading.Thread(target=send_request, daemon=True).start()
    
    def clear_debug_inputs(self):
        """清空调试输入框"""
        self.debug_amount_entry.delete(0, tk.END)
        self.debug_amount_entry.insert(0, "0.01")
        
        self.debug_memo_entry.delete(0, tk.END)
        self.debug_memo_entry.insert(0, "测试备注")
        
        self.debug_order_entry.delete(0, tk.END)
        
        self.debug_payer_memo_entry.delete(0, tk.END)
        
        self.log_message("[调试] 已清空输入框")
    # --- 调试功能方法结束 ---

    def on_closing(self):
        """处理窗口关闭事件"""
        if self.is_monitoring:
            if messagebox.askokcancel("退出", "监控正在进行中，确定要退出吗？"):
                self.is_monitoring = False
                if self.monitoring_thread and self.monitoring_thread.is_alive():
                    self.monitoring_thread.join(timeout=2)
                self.destroy()
            else:
                return # 取消关闭
        else:
           self.destroy()

# --- 鼠标区域选择辅助类 ---
class MouseRegionSelector:
    def __init__(self, gui_window):
        self.gui_window = gui_window
        self.listener = None
        self.first_click_pos = None

    def on_click(self, x, y, button, pressed):
        """处理鼠标点击事件"""
        if button == mouse.Button.left:
            if pressed:
                if self.first_click_pos is None:
                    # 第一次点击，记录起点
                    self.first_click_pos = (x, y)
                    logger.debug(f"鼠标按下于 ({x}, {y})。")
                # else: 忽略按下拖拽
            else: # released
                if self.first_click_pos is not None:
                    # 第二次点击释放，计算区域
                    end_x, end_y = x, y
                    start_x, start_y = self.first_click_pos

                    # 计算区域参数 (确保宽高为正)
                    left = min(start_x, end_x)
                    top = min(start_y, end_y)
                    width = abs(end_x - start_x)
                    height = abs(end_y - start_y)

                    if width > 0 and height > 0:
                        region = {"left": left, "top": top, "width": width, "height": height}
                        self.gui_window.selected_region = region
                        self.gui_window.coord_entry.delete(0, tk.END)
                        self.gui_window.coord_entry.insert(0, f"{left},{top},{width},{height}")
                        self.gui_window.log_message(f"已选择监控区域: {region}")
                        self.gui_window.region_selected = True
                    else:
                        self.gui_window.log_message("选择的区域无效 (宽度或高度为0)，请重新选择。")

                    # 重置状态
                    self.first_click_pos = None
                    # 停止监听
                    return False # 返回 False 会停止监听器

    def start_listening(self):
        """启动鼠标监听"""
        self.first_click_pos = None # 重置
        self.listener = mouse.Listener(on_click=self.on_click)
        self.listener.start()
        logger.debug("鼠标监听器已启动。")

    def stop_listening(self):
        """停止鼠标监听"""
        if self.listener:
            self.listener.stop()
            logger.debug("鼠标监听器已停止。")


# --- Flask API 服务器 ---
from flask import Flask, request, jsonify
from flask_cors import CORS
import threading
# 导入处理时间戳所需的库
import time
from datetime import datetime

app = Flask(__name__)
CORS(app)  # 允许所有跨域请求

# --- 新增：用于存储支付记录的全局列表 ---
payment_records = []
# ----------------------------------------


@app.route('/receive_payment', methods=['POST'])
def receive_payment():
    """接收来自监控线程的OCR支付通知，并返回处理后的信息"""
    try:
        data = request.get_json()
        if not data:
            logger.warning("收到空的JSON数据或非JSON数据")
            return jsonify({"status": "error", "message": "No valid JSON data received"}), 400

        logger.info(f"收到支付通知: {data}")

        # --- 数据提取与基础处理 ---
        raw_order_id = data.get("order_id", "N/A")
        raw_amount_str = data.get("amount", "0.00")
        payer_memo = data.get("payer_memo", "")
        user_memo = data.get("user_memo", "")
        timestamp_int = data.get("timestamp")

        # --- 核心业务逻辑处理 ---

        # 1. 处理金额 (字符串 -> 浮点数)
        try:
            amount_float = float(raw_amount_str)
            formatted_amount = f"{amount_float:.2f}" # 格式化为保留两位小数的字符串
        except ValueError:
            logger.warning(f"无效的金额格式: {raw_amount_str}")
            formatted_amount = "0.00" # 或者返回错误？

        # 2. 处理时间戳 (整数秒 -> 人类可读格式)
        logger.debug(f"[DEBUG] 收到的 timestamp_int: {timestamp_int}, 类型: {type(timestamp_int)}")
        readable_time = None
        
        # 尝试多种方式解析时间戳
        if timestamp_int is not None:
            try:
                # 尝试转换为整数（处理字符串或浮点数的情况）
                ts_value = int(timestamp_int) if not isinstance(timestamp_int, int) else timestamp_int
                # 转换为本地时间
                readable_time = datetime.fromtimestamp(ts_value).strftime('%Y-%m-%d %H:%M:%S')
                logger.debug(f"[DEBUG] 成功转换时间戳: {ts_value} -> {readable_time}")
            except (ValueError, OSError, TypeError) as e:
                logger.warning(f"时间戳转换失败: {timestamp_int}, 错误: {e}")
        
        # 如果时间戳解析失败，使用当前系统时间作为回退
        if readable_time is None:
            readable_time = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            logger.debug(f"[DEBUG] 使用当前系统时间作为回退: {readable_time}")

        # 3. (可选) 订单ID处理，比如去除前缀等
        processed_order_id = raw_order_id # 这里可以添加逻辑

        # 4. (可选) 备注处理，比如清理、截断等
        # 你之前写的清理和截断逻辑可以放在这里应用到 payer_memo 或 user_memo 上

        # --- 构造返回给客户端的响应数据 ---
        response_data = {
            "status": "success",
            "processed_payment_info": { # 使用更描述性的键名
                "order_id": processed_order_id,
                "actual_amount": formatted_amount, # 返回格式化后的金额
                "payment_time": readable_time,     # 返回格式化后的时间
                "payer_memo": payer_memo,
                "user_memo": user_memo,            # 返回处理后的用户备注
                # 可以添加更多处理后的信息
                # "net_amount": net_amount, # 例如，扣除手续费后的净额
                # "currency": "CNY"         # 货币单位
            },
            # (可选) 也可以返回原始收到的数据
            # "original_data_received": data
        }

        # ***** 在这里添加保存记录的代码 *****
        payment_records.append(response_data["processed_payment_info"]) # 将处理后的信息添加到全局列表
        # ************************************

        logger.info(f"处理完成，返回信息: {response_data['processed_payment_info']}")
        return jsonify(response_data), 200

    except Exception as e:
        logger.error(f"处理支付通知时发生未预期错误: {e}", exc_info=True)
        return jsonify({"status": "error", "message": "Internal server error during processing"}), 500

# ***** 添加查询所有记录的端点 *****
@app.route('/query_payment', methods=['GET'])
def query_payment():
    """提供一个查询接口，返回所有已存储的支付记录"""
    global payment_records # 声明使用全局变量

    # 返回所有记录
    # 注意：对于大量数据，可能需要考虑分页
    return jsonify({
        "status": "success",
        "total_count": len(payment_records), # 可选：返回总记录数
        "records": payment_records           # 返回存储的所有记录
    }), 200
# *********************************

# --- run_flask_app 函数 ---
def run_flask_app():
    """运行Flask应用"""
    # 注意：host='0.0.0.0' 使其对外网可见，生产环境需谨慎
    # debug=False 避免与主GUI线程冲突，并防止代码重载带来的问题
    app.run(host='0.0.0.0', port=5001, debug=False)

# --- 主程序入口 ---
if __name__ == "__main__":
    # 启动Flask API服务器线程
    flask_thread = threading.Thread(target=run_flask_app, daemon=True)
    flask_thread.start()
    logger.info("Flask API服务器线程已在 http://0.0.0.0:5001 启动")

    # 创建并运行GUI主窗口
    root = NotificationWindow()
    # 将GUI实例赋给全局变量，供Flask API访问 (虽然目前未使用)
    notification_window_instance = root
    root.protocol("WM_DELETE_WINDOW", root.on_closing) # 绑定关闭事件
    logger.info("GUI应用程序已启动。")
    root.mainloop()

    logger.info("应用程序关闭完成。")
