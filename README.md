# 📐 工程图纸智能脱敏系统 (Engineering Drawing Desensitizer)

<p align="center">
  <img src="https://img.shields.io/badge/Python-3.11+-blue.svg?style=flat-square" alt="Python Version" />
  <img src="https://img.shields.io/badge/GUI-PyQt5-green.svg?style=flat-square" alt="PyQt5" />
  <img src="https://img.shields.io/badge/PDF_Engine-PyMuPDF_1.27+-orange.svg?style=flat-square" alt="PyMuPDF" />
  <img src="https://img.shields.io/badge/OCR-RapidOCR_ONNX-purple.svg?style=flat-square" alt="RapidOCR" />
  <img src="https://img.shields.io/badge/Tests-74%20Passed-brightgreen.svg?style=flat-square" alt="Tests" />
  <img src="https://img.shields.io/badge/License-MIT-yellow.svg?style=flat-square" alt="License" />
</p>

<p align="center">
  <strong>一款专为工业制造、工程设计行业打造的本地离线 PDF 图纸脱敏桌面工具。</strong><br>
  结合矢量解析、深度 OCR 与计算机视觉三通道检测，配备自研表格框线智能归位算法，实现<strong>严格不越框污染图纸有效尺寸、公差与技术要求</strong>的精准脱敏。
</p>

---

## ✨ 核心特性

- 🔒 **100% 纯本地离线计算**：零云端请求、零外部网络交互，完全杜绝企业核心技术资产与客户工程图纸的外泄风险。
- ⚡ **三通道多模态智能检测**：
  - **矢量文本通道 (Vector Channel)**：基于 PyMuPDF 底层字符 Span 流，毫秒级精准捕获原始文字坐标。
  - **栅格 OCR 通道 (OCR Channel)**：内置 RapidOCR-onnxruntime 离线轻量级引擎，高效识别扫描件、光栅图与批注文字。
  - **图形视觉通道 (Visual Channel)**：XObject 图片对象分析 + OpenCV 多尺度模板匹配，快速锁定敏感 Logo。
- 🎯 **自研表格框线智能归位 (Box Finder)**：
  - 传统 OCR 框容易发生边缘溢出或局部残留。本系统可自动检测图纸标题栏/表格的最小封闭单元格，将检测框向上吸附归位至单元格物理边界；
  - 确保擦除范围严密受限于方框内部，**绝不越框污染图纸几何线、尺寸标注与技术要求**。
- ✂️ **物理级矢量真删除 (ERASE 模式)**：
  - 底层调用 PDF Redaction 物理删除内容流（Content Stream），彻底移除敏感文本与矢量数据，无法被逆向提取；同时支持可选的“安全覆盖 (COVER)”遮挡模式。
- ⚙️ **灵活解耦的外部规则库**：
  - 支持通过外部配置文件 ules/sensitive_terms.txt 或 GUI 界面自由配置敏感词表与视觉模板，开箱即用。

---

## 🏗️ 系统架构设计

`mermaid
flowchart TD
    A[客户原始 PDF 工程图纸] --> B{多模态检测引擎}
    
    subgraph Detection [三通道检测]
        B -->|矢量层提取| C1[PyMuPDF 矢量文本检测]
        B -->|300 DPI 离线渲染| C2[RapidOCR 栅格文字识别]
        B -->|XObject / 模板匹配| C3[OpenCV 图形/Logo 检索]
    end
    
    C1 --> D[空间坐标系统一 & IoU 去重融合]
    C2 --> D
    C3 --> D
    
    D --> E[规则匹配过滤 - 敏感词库 / 保密标记]
    E --> F[自研 BoxFinder 智能框线归位]
    
    F -->|单元格吸附| G[安全脱敏执行器 (PDF Redaction)]
    
    G --> H[输出: 原名_desensitized.pdf]
`

---

## 🚀 快速上手

### 环境要求
- 操作系统：Windows 10/11, macOS, Linux
- Python 版本：Python 3.10 或 3.11

### 1. 克隆与安装依赖

`ash
# 克隆仓库
git clone https://github.com/zonlic0925-boop/Desensitization.git
cd Desensitization

# 安装依赖
pip install -r requirements.txt
`

### 2. 启动图形交互界面 (GUI)

- **Windows 一键启动**：双击根目录下的 启动系统.bat。
- **命令行启动**：
  `ash
  python main_ui.py
  `

---

## 🖥️ 界面与交互能力

- **单张精细预览与即时脱敏**：
  - 支持单页/多页图纸分页浏览与多级缩放；
  - 实时高亮显示检测到的敏感命中项（不同颜色区分矢量、OCR、Logo）；
  - 支持单图纸即时脱敏并直接查看脱敏后矢量渲染效果。
- **批量一键流水线处理**：
  - 支持批量添加图纸文件或文件夹导入；
  - 实时显示批处理进度条与成功/失败/跳过统计日志。
- **内置推荐通用保密规则**：
  - 界面提供 ✨ 恢复推荐通用保密规则 按钮，一键载入国际工程图纸通用保密词（如 CONFIDENTIAL, PROPRIETARY, RESTRICTED, INTERNAL USE ONLY 等）。

---

## ⚙️ 规则配置说明

本系统遵循代码与业务数据解耦原则，所有脱敏规则均可通过文件或界面动态更新：

1. **敏感词库配置 (ules/sensitive_terms.txt)**：
   每行一个敏感词或正则表达式，系统自动忽略空行与 # 注释行：
   `	ext
   # 常用保密词
   CONFIDENTIAL
   PROPRIETARY
   RESTRICTED
   DO NOT DISTRIBUTE
   
   # 自定义公司或供应商名称
   ACME CORPORATION
   SAMPLE TECH
   `
2. **图形 Logo 模板 (ules/logos/)**：
   将需要检测的企业 Logo（PNG/JPG 格式）放入该目录，系统将在图纸检测时自动进行多尺度模板匹配与定位。

---

## 🧪 单元测试

项目包含完善的自动化测试套件（覆盖检测器、规则引擎、管道流、执行器、UI及发布契约）：

`ash
pytest
`

---

## 📄 开源许可证

本项目采用 [MIT License](LICENSE) 许可协议。
