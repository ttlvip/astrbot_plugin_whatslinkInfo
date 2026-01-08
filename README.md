
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
- **智能反风控**:
  - 优先在图片边缘添加黑色图案，尽量保留主体清晰
  - 动态噪声会按失败次数自动加重，直到发送成功
  - 多种噪声类型：彩色条纹、像素噪声、渐变叠加、几何图案、局部模糊、波纹变形等
  - 智能降级策略：原图 → 拼接图 → 边缘图案 → 动态噪声变体 → 纯文本
  - 每次生成独特的噪声模式，难以被学习和记忆
  - 发送失败时可保存处理后的图片用于排查
- **智能发送**:
  - 在 QQ/OneBot 平台下，可配置使用**合并转发**的形式发送，避免长消息刷屏。
  - 自动引用原始消息进行回复，交互清晰。
  - 发送"解析中"的提示后**自动撤回**，保持聊天界面整洁。

## 💿 安装

在 AstrBot  插件市场搜索 `astrbot_plugin_whatslinkinfo` 并安装。

## 📖 使用方法

在任意聊天中发送包含磁力链接的消息即可。插件会自动处理并回复预览信息。

## 🔁 执行流程（含噪声策略）

收到磁链后，插件按以下顺序尝试发送，失败则自动增强干扰：

1. 发送多张原图（合并转发）
2. 发送拼接长图（合并转发）
3. 发送边缘黑色图案（合并转发）
   - 边缘图案在图片外侧扩边，不覆盖原图内容
   - `edge_ratio` 仅作为“上限”，插件会从轻到重逐级增加边缘比例
   - 当前内置为 3 个级别：`0.5x → 0.75x → 1.0x`（相对于 `edge_ratio` 上限）
   - 黑色图案为边缘区域的块状/条块分布，主体区域不受影响
4. 发送动态噪声（合并转发）
   - 自动按 `minimal → balanced → aggressive` 逐级增强
   - 每一级内部会生成少量变体依次尝试（当前内置为 2 张/级）
   - 噪声是叠加在拼接图上的，不影响原图下载步骤
5. 仍失败则回落为纯文本

若所有图像策略失败且开启 `save_failed_images`，会保存处理后的图片用于排查。

### 🎛️ 噪声类型与强度说明

动态噪声会在拼接图基础上叠加以下类型（每次随机化位置/强度）：

- 像素噪声：随机采样像素点，覆盖约 5%~30%；被扰动像素概率约 10%~80%；颜色偏移约 ±50 或反相 30%~70% 强度
- 渐变叠加：低透明度渐变覆盖，方向随机（横/竖/径向/圆形），强度范围约 0.1~0.8
- 彩色条纹：3~8 条彩色条带，宽约 20~150 像素，高约 10~80 像素，可能倾斜 -30~30 度或平行分布
- 几何图案：5~15 个小型圆/矩形/线条/点阵，尺寸约 20~100 像素，透明度随强度变化
- 局部模糊：2~5 个小块模糊，单块尺寸约 30~150 像素，模糊半径约 1~5
- 波纹变形：轻微正弦位移变形，振幅约 5~20 像素，频率约 0.01~0.05

噪声强度按级别递增：

- **minimal（轻）**：单一噪声类型（像素噪声或渐变叠加）
- **balanced（中）**：两种噪声组合（条纹+像素、渐变+几何、像素+模糊、渐变+波纹）
- **aggressive（重）**：三种噪声组合（条纹+像素+模糊、渐变+几何+波纹、条纹+模糊+波纹、几何+模糊+像素）

每一级会生成不同随机变体，失败才会进入下一等级。

## ⚙️ 配置项

你可以在 AstrBot  的插件配置页面找到本插件的设置项。

| 配置项              | 类型      | 默认值                               | 描述                                                               |
| ------------------- | --------- | ------------------------------------ | ------------------------------------------------------------------ |
| `timeout`           | `number`  | `10000`                              | 请求 API 的超时时间（毫秒）。                                      |
| `useForward`        | `boolean` | `true`                               | 在 QQ/OneBot 平台使用合并转发的形式发送结果。                      |
| `showScreenshot`    | `boolean` | `true`                               | 是否在结果中显示资源截图。                                         |
| `max_stitch_count`  | `number`  | `4`                                  | 拼接长图时最多使用的图片数量。                                     |
| `edge_ratio`        | `number`  | `0.06`                               | 边缘黑色图案厚度占短边的上限比例（0.01-0.2）。                     |
| `save_failed_images` | `boolean` | `true`                              | 拼接/边缘/噪声发送失败时保存处理后的图片。                         |
| `failed_images_dir` | `string`  | `failed_images`                      | 保存目录（相对插件目录或绝对路径）。                               |



## 📜 免责声明

本插件仅作为技术学习和研究目的，所有数据均来源于第三方 API ([whatslink.info](https://whatslink.info/))。

插件作者不存储、不分发、不制作任何资源文件，也不对通过磁力链接获取的内容的合法性、安全性、准确性负责。

反风控噪声功能仅用于解决平台的技术限制，避免误判导致的正常内容无法展示。请用户在使用本插件时，严格遵守当地法律法规。任何因使用本插件而产生的法律后果，由用户自行承担。

## 📝 许可

[MIT License](https://github.com/ttlvip/astrbot_plugin_whatslinkInfo/blob/master/LICENSE) © 2025 ttlvip
