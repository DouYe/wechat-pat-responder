# 微信拍一拍随机回复器

这是一个实验性的 Windows 桌面自动化程序。它用 Windows OCR 扫描微信左侧
可见会话列表；发现新的 `tickled m`（同时匹配 `tickled me` 和
`tickled my`）后，打开对应会话并发送随机回复。

[直接下载 Windows 版本](https://github.com/DouYe/wechat-pat-responder/releases/latest/download/WeChatPatResponder-Windows-x64.zip)
· [English](README.md)

## 功能

- 监控左侧可见会话，不要求目标会话已经打开。
- 目标已经是当前会话时跳过点击，避免把会话点成未选中。
- 记录微信显示时间和本机检测时间。
- 支持连续拍、持久计数和 2.5 秒最短去重。
- 随机行为：抽象短句、计数器、连击、假系统文字、红包兑奖彩蛋。
- 红包彩蛋只发文字，不会执行支付。
- 不修改微信、不注入 DLL、不读取聊天数据库。

## 支持范围

发行包支持 **64 位 Windows 10/11**。程序依赖 Windows 微信、Windows OCR、
窗口截图和 Windows 输入接口，因此不能原生运行在 macOS、Linux 或 Chromebook。
其他系统可以连接一台常开的 Windows 主机或使用 Windows 虚拟机。

## 最快安装方式

1. 安装并登录官方 Windows 微信/Weixin。
2. 安装英文 OCR：
   - 设置 → 时间和语言 → 语言和区域；
   - 添加“英语（美国）”及其语言功能；
   - 或下载源码后，以管理员身份运行 `Install-OCR.cmd`。
3. 下载并解压
   [WeChatPatResponder-Windows-x64.zip](https://github.com/DouYe/wechat-pat-responder/releases/latest/download/WeChatPatResponder-Windows-x64.zip)。
4. 保持微信主窗口打开且没有最小化。
5. 双击 `Run.cmd`。
6. 点击“开始监控”。首次扫描只建立基线，需要让对方重新拍一次。

由于程序未购买代码签名证书，Windows SmartScreen 可能显示警告。介意的话请先
检查源码并自行构建。

## 从源码安装

需要 64 位 Python 3.10 或更新版本。下载源码后双击：

```bat
Setup.cmd
```

脚本会创建独立 `.venv`、安装依赖、检查 OCR 并启动程序。以后使用
`Run.cmd` 即可。

如果 OCR 检查失败，请以管理员身份运行：

```bat
Install-OCR.cmd
```

完成后重启 Windows。也可以参考微软的
[Windows 语言包说明](https://support.microsoft.com/zh-cn/windows/windows-%E7%9A%84%E8%AF%AD%E8%A8%80%E5%8C%85-a5094319-a92d-18de-5b53-1cfc697cfca8)。

## 排错

- 点击“单次 OCR 测试”，确认左栏预览中能读到 `tickled m`。
- 目标会话必须出现在左侧可见区域。
- 微信可以被其他窗口遮挡，但不能最小化。
- OCR 读不到时，尝试放大微信窗口和左侧会话栏。
- 微信更新界面后，OCR 区域和点击位置可能需要调整。

## 风险说明

这不是微信官方接口。自动点击可能因 OCR 或界面变化选错会话；程序还会覆盖目标
输入框内尚未发送的文字。建议先用备用号测试，并阅读 [SECURITY.md](SECURITY.md)。

## 数据文件

- `tickle_events.log`：检测历史
- `tickle_state.json`：各会话累计次数和连击状态

项目采用 MIT License，与腾讯、微信、Weixin 无关联。
