import easyocr
import re
import numpy as np
from PIL import Image, ImageTk
import tkinter as tk
from tkinter import filedialog, messagebox, scrolledtext
from collections import defaultdict
from timeit import default_timer as timer
from tkinter import ttk
import torch
import matplotlib.pyplot as plt
#import cv2

# 建立 OCR reader
reader = easyocr.Reader(['en'])

def clear_gpu_memory():
    if torch.cuda.is_available():
        torch.cuda.empty_cache()
        torch.cuda.ipc_collect()

def Hazard_Avoid(img):
    resize_img = np.array(img)
    Size = resize_img.shape[0] * resize_img.shape[1]

    if Size > 650 * 1200:  # 需要解除特徵
        if (resize_img.shape[0]<resize_img.shape[1]):
            resize_ratio_1 = resize_img.shape[0] / 650
            resize_ratio_2 = resize_img.shape[1] / 1200
            resize_ratio_1 = int(resize_ratio_1)+1
            resize_ratio_2 = int(resize_ratio_2)+1
            
            if resize_ratio_1 > 1:
                resize_img = resize_img[::resize_ratio_1, :]  # 每 數 行取 1 行
            if resize_ratio_2 > 1:
                resize_img = resize_img[:, ::resize_ratio_2]  # 每 數 列取 1 列
        else:
            resize_ratio_1 = resize_img.shape[1] / 650
            resize_ratio_2 = resize_img.shape[0] / 1200
            resize_ratio_1 = int(resize_ratio_1)+1
            resize_ratio_2 = int(resize_ratio_2)+1
            if resize_ratio_1>1:
                resize_img = resize_img[::resize_ratio_2, :]  # 每 數 列取 1 列
            if resize_ratio_2 > 1:
                resize_img = resize_img[:, ::resize_ratio_1]  # 每 數 行取 1 行
    img = Image.fromarray(resize_img)
    return img
 
# 核心函數：判斷是否合法算式並計算
def calculator(expression):
    Answer_List = []
    dict_A = {"l":'1',"Z":'2',"q":'9','x':'*','X':'*'}
    for item in expression:
        s = item[1]
        corrected = ''.join(dict_A.get(c, c) for c in s)
        #corrected = s
        if re.fullmatch(r'[\d\s\+\-\*\/\(\)]+', corrected):
            try:
                result = eval(corrected)
                if (str(result)!=corrected):
                    Answer_List.append((corrected, result))
            except:
                continue
    return Answer_List

def normalize_angle(angle):
    angle = angle % 360
    if angle >= 180:
        angle -= 360
    return angle

def filter_by_angle_span(results, threshold=120):
    expr_groups = defaultdict(list)
    for angle, expr, val in results:
        expr_groups[expr].append((normalize_angle(angle), expr, val))

    final_filtered = []
    for expr, group in expr_groups.items():
        group.sort()
        angles = [a for a, _, _ in group]
        span = max(angles) - min(angles)
        if span > threshold:
            final_filtered.extend(group)
        else:
            final_filtered.append(group[0])
    return final_filtered

# 更新版 analyze_image：用 GUI 進度條取代 tqdm
def analyze_image(path, output_widget, progress_bar):
    try:
        img = Image.open(path)
        img = Hazard_Avoid(img)
    except:
        messagebox.showerror("錯誤", "無法開啟圖片！")
        return

    all_results = []
    start_time = timer()

    total_steps = 8
    progress_bar["maximum"] = total_steps
    progress_bar["value"] = 0
    output_widget.delete('1.0', tk.END)
    
    for i in range(total_steps):
        angle = i * (360/total_steps)
        rotated_img = img.rotate(angle, expand=True)
        
        np_img = np.array(rotated_img)
        result = reader.readtext(np_img)
        print("result: ",result)
        answers = calculator(result)
        if answers:
            for expr, val in answers:
                all_results.append((angle, expr, val))
        # 更新進度條
        progress_bar["value"] = i + 1
        output_widget.update_idletasks()
        progress_bar.update_idletasks()

    end_time = timer()
    if not all_results:
        output_widget.insert(tk.END, "沒有找到合法的數學式！")
    else:
        filtered = filter_by_angle_span(all_results)
        output_widget.insert(tk.END, "找到的算式（篩選後）:\n")
        for angle, expr, val in filtered:
            output_widget.insert(tk.END, f"[{angle} 度] {expr} = {val}\n")
        output_widget.insert(tk.END, f"\nTime usage: {end_time - start_time:.2f} 秒")
    clear_gpu_memory()

def open_file(output_widget, progress_bar):
    filepath = filedialog.askopenfilename(filetypes=[("Image Files", "*.jpg *.jpeg *.png")])
    if filepath:
        analyze_image(filepath, output_widget, progress_bar)

def launch_gui():
    root = tk.Tk()
    root.title("數學式 OCR 辨識工具")
    root.geometry("500x300")

    tk.Label(root, text="請選擇一張圖片進行 OCR 辨識", font=("Arial", 14)).pack(pady=10)

    output = scrolledtext.ScrolledText(root, width=60, height=8, font=("Courier", 10))
    output.pack(padx=10, pady=10)

    # 新增進度條
    progress_bar = ttk.Progressbar(root, orient="horizontal", length=400, mode="determinate")
    progress_bar.pack(pady=5)

    tk.Button(root, text="選擇圖片", command=lambda: open_file(output, progress_bar), font=("Arial", 12)).pack()

    root.mainloop()
    
launch_gui()