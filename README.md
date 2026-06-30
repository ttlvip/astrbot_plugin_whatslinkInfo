
<div align="center">

![:name](https://count.getloli.com/@astrbot_plugin_whatslinkInfo?name=astrbot_plugin_whatslinkInfo&theme=rule34&padding=6&offset=0&align=top&scale=1&pixelated=1&darkmode=auto)

# astrbot_plugin_whatslinkInfo

_✨ [astrbot](https://github.com/AstrBotDevs/AstrBot) 磁链解析插件 v2.0.0 ✨_

[![License](https://img.shields.io/badge/License-MIT-green.svg)](https://opensource.org/licenses/MIT)
[![Python 3.10+](https://img.shields.io/badge/Python-3.10%2B-blue.svg)](https://www.python.org/)
[![AstrBot](https://img.shields.io/badge/AstrBot-3.4%2B-orange.svg)](https://github.com/Soulter/AstrBot)
[![GitHub](https://img.shields.io/badge/作者-ttlvip-blue)](https://github.com/ttlvip)

</div>

<h1>项目由完全由ai完成，并且由于工作原因，不定时更新和修bug。目前还处于不可用状态</h1>

一个 [Astrbot](https://github.com/AstrBotDevs/AstrBot) 插件，它能自动识别聊天中的磁力链接，并调用 [whatslink.info](https://whatslink.info/) 提供的 API 来生成包含资源详情和截图的预览消息。

## ✨ 功能特性

- **自动识别**: 无需任何指令，在聊天中发送磁力链接即可自动触发（支持唤醒词控制）。
- **信息丰富**: 显示资源的名称、文件数量、总大小和内容类型。
- **截图预览**: 可配置是否显示由 API 提供的资源截图；支持垂直拼接与高斯模糊处理。
- **智能发送**:
  - 在 QQ/OneBot 平台下，可配置使用**合并转发**的形式发送，避免长消息刷屏。
  - 自动引用原始消息进行回复，交互清晰。
  - 发送"解析中"的提示后由框架管理生命周期，保持聊天界面整洁。
- **命令系统**: 提供 `help`、`test`、`config` 三条辅助命令，方便调试与查看配置。

## 💿 安装

在 AstrBot 插件市场搜索 `astrbot_plugin_whatslinkinfo` 并安装。

> **依赖说明**: 截图拼接与模糊功能依赖 [Pillow](https://python-pillow.org/)（≥10.0.0）。  
> 若未安装 Pillow，截图拼接与模糊功能将自动禁用，其他功能不受影响。  
> 可通过 `pip install Pillow` 手动安装。

## 📖 使用方法

### 自动触发

在任意聊天中发送包含磁力链接（`magnet:?xt=urn:btih:...`）的消息即可。插件会自动处理并回复预览信息。

> **唤醒词控制**: 当 `no_wake_word` 为 `false`（默认）时，在群聊中需要以 `/` 命令方式或 @机器人 才会触发磁链解析；私聊中始终触发。  
> 设置为 `true` 则任意包含磁链的消息都会触发。

### 命令交互

| 命令 | 说明 |
|------|------|
| `/whatslink help` | 查看插件功能说明、命令列表与当前配置 |
| `/whatslink test <magnet_link>` | 手动测试某个磁力链接的解析结果 |
| `/whatslink config` | 查看当前插件的完整配置值 |

---

### 命令详细文档

#### 1. `/whatslink help` — 帮助命令

- **使用场景**: 首次使用插件时查看功能概述；不确定当前配置时快速确认。
- **何时调用**: 需要了解插件能力、查看命令列表或检查当前配置状态。
- **参数**: 无
- **示例用法**:
  ```
  /whatslink help
  ```
- **返回内容**: 插件简介、三条命令的说明、当前所有配置项的实时值、配置修改路径。

#### 2. `/whatslink test <magnet_link>` — 测试命令

- **使用场景**: 手动验证某个磁力链接能否被正确解析；调试 API 连通性；测试截图拼接/模糊效果。
- **何时调用**: 怀疑自动解析未生效时手动触发；想查看特定磁链的返回数据格式。
- **参数**:
  | 参数 | 类型 | 必填 | 说明 |
  |------|------|------|------|
  | `magnet_link` | string | 是 | 完整的磁力链接 URL，必须以 `magnet:?xt=urn:btih:` 开头 |
- **示例用法**:
  ```
  /whatslink test magnet:?xt=urn:btih:ABCDEF1234567890ABCDEF1234567890ABCDEF
  ```
- **返回内容**: 先发送"正在解析磁链..."提示，随后返回与自动触发相同的格式化预览消息（含截图等）。

#### 3. `/whatslink config` — 配置查看命令

- **使用场景**: 在不打开 AstrBot 管理后台的情况下快速确认插件当前配置。
- **何时调用**: 排查解析行为异常时检查配置；确认某项功能是否已启用。
- **参数**: 无
- **示例用法**:
  ```
  /whatslink config
  ```
- **返回内容**: 六项配置的当前值，以及 Pillow 的安装状态提示。

---

## ⚙️ 配置项

所有配置通过 AstrBot WebUI 管理：**插件管理 → 点击 `astrbot_plugin_whatslinkInfo`**。
插件目录下的 `_conf_schema.json` 定义了配置 Schema，修改后即时生效。

| 配置项 | 类型 | 默认值 | 说明 |
|--------|------|--------|------|
| `merge_forward` | `boolean` | `false` | 在 QQ/OneBot 平台使用合并转发的形式发送结果。开启后多张截图将在转发消息中逐张展示；关闭后截图将垂直拼接为一张图片。 |
| `no_wake_word` | `boolean` | `false` | 是否免唤醒词触发。`true` = 任意消息中的磁链都会触发解析；`false` = 群聊中仅响应命令消息（`/` 开头）或 @机器人，私聊始终触发。 |
| `timeout` | `integer` | `10` | 请求 whatslink.info API 的超时时间（秒）。网络较差时可适当调大。 |
| `show_screenshots` | `boolean` | `true` | 是否在解析结果中显示资源截图。关闭后仅返回文本信息（名称、文件数量、大小）。 |
| `blur_screenshots` | `boolean` | `false` | 是否对截图进行高斯模糊处理。开启后所有截图将先模糊再发送。**依赖 Pillow**。 |
| `blur_intensity` | `integer` | `3` | 截图模糊强度等级，取值范围 **1-9**。数值越大模糊程度越高。仅当 `blur_screenshots=true` 时生效。 |

### 特殊显示逻辑说明

| 条件 | 行为 |
|------|------|
| `show_screenshots=true` + `merge_forward=false` | 多张截图**垂直拼接**为一张图片后发送。拼接时保持各截图原始宽高比，以最大宽度为画布宽度，图片间水平居中排列。 |
| `show_screenshots=true` + `merge_forward=true` | 所有截图在合并转发消息中逐张展示（不拼接）。 |
| `blur_screenshots=true` | 在拼接（或转发）之前对每张截图执行高斯模糊，模糊半径 = `blur_intensity` 值。 |
| `show_screenshots=false` | 不下载、不处理、不显示任何截图。 |

### 配置示例

在 AstrBot WebUI 插件管理页面中直接修改即可，无需编辑配置文件。

## 🔧 依赖

| 依赖 | 版本要求 | 用途 |
|------|----------|------|
| `aiohttp` | ≥3.9.0 | 异步 HTTP 请求（API 调用 + 截图下载） |
| `Pillow` | ≥10.0.0 | 截图拼接与高斯模糊（可选，未安装时相关功能自动禁用） |

## 📜 免责声明

本插件仅作为技术学习和研究目的，所有数据均来源于第三方 API ([whatslink.info](https://whatslink.info/))。

插件作者不存储、不分发、不制作任何资源文件，也不对通过磁力链接获取的内容的合法性、安全性、准确性负责。

请用户在使用本插件时，严格遵守当地法律法规。任何因使用本插件而产生的法律后果，由用户自行承担。

## 📝 许可

[MIT License](https://github.com/ttlvip/astrbot_plugin_whatslinkInfo/blob/master/LICENSE) © 2025 ttlvip

<div align="center">

![:name](https://count.getloli.com/@astrbot_plugin_whatslinkInfo?name=astrbot_plugin_whatslinkInfo&theme=rule34&padding=6&offset=0&align=top&scale=1&pixelated=1&darkmode=auto)

# astrbot_plugin_whatslinkInfo

_✨ [astrbot](https://github.com/AstrBotDevs/AstrBot) 磁链解析插件 ✨_  

[![License](https://img.shields.io/badge/License-MIT-green.svg)](https://opensource.org/licenses/MIT)
[![Python 3.10+](https://img.shields.io/badge/Python-3.10%2B-blue.svg)](https://www.python.org/)
[![AstrBot](https://img.shields.io/badge/AstrBot-3.4%2B-orange.svg)](https://github.com/Soulter/AstrBot)
[![GitHub](https://img.shields.io/badge/作者-ttlvip-blue)](https://github.com/ttlvip)

</div>


一个[Astrbot](https://github.com/AstrBotDevs/AstrBot)插件，它能自动识别聊天中的磁力链接，并调用 [whatslink.info](https://whatslink.info/) 提供的 API 来生成包含资源详情和截图的预览消息。

## ✨ 功能特性

- **自动识别**: 无需任何指令，在聊天中发送磁力链接即可自动触发。
- **信息丰富**: 显示资源的名称、总大小、文件数量和内容类型。
- **截图预览**: 可配置是否显示由 API 提供的资源截图。
- **智能发送**:
  - 在 QQ/OneBot 平台下，可配置使用**合并转发**的形式发送，避免长消息刷屏。
  - 自动引用原始消息进行回复，交互清晰。
  - 发送“解析中”的提示后**自动撤回**，保持聊天界面整洁。

## 💿 安装

在 AstrBot  插件市场搜索 `astrbot_plugin_whatslinkinfo` 并安装。

## 📖 使用方法

在任意聊天中发送包含磁力链接的消息即可。插件会自动处理并回复预览信息。

## ⚙️ 配置项

你可以在 AstrBot  的插件配置页面找到本插件的设置项。

| 配置项           | 类型      | 默认值                               | 描述                                                               |
| ---------------- | --------- | ------------------------------------ | ------------------------------------------------------------------ |
| `timeout`        | `number`  | `10000`                              | 请求 API 的超时时间（毫秒）。                                      |
| `useForward`     | `boolean` | `false`                              | 在 QQ/OneBot 平台使用合并转发的形式发送结果。                      |
| `showScreenshot` | `boolean` | `true`                               | 是否在结果中显示资源截图。                                         |



## 📜 免责声明

本插件仅作为技术学习和研究目的，所有数据均来源于第三方 API ([whatslink.info](https://whatslink.info/))。

插件作者不存储、不分发、不制作任何资源文件，也不对通过磁力链接获取的内容的合法性、安全性、准确性负责。

请用户在使用本插件时，严格遵守当地法律法规。任何因使用本插件而产生的法律后果，由用户自行承担。

## 📝 许可

[MIT License](https://github.com/ttlvip/astrbot_plugin_whatslinkInfo/blob/master/LICENSE) © 2025 ttlvip
