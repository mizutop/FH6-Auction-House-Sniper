[![在 Ko-fi 上支持](https://img.shields.io/badge/Support_on-Ko--fi-FF5E5B?logo=ko-fi&logoColor=white)](https://ko-fi.com/frostyisbored) [![需要帮助？加入 Discord](https://img.shields.io/badge/Need_help%3F-Join_the_Discord-5865F2?logo=discord&logoColor=white)](https://discord.gg/PWPmVWdP8r)
# FH6 拍卖行狙击工具

> ### ⚡ 这是免费版本——如需优化版，请查看 [**FH6 Sniper V2**](https://fh6sniper.com)
>
> 我会持续维护此免费版本，提供**错误修复**和游戏更新的补丁。
>
> **V2** 是经过重建和优化的狙击版本，**更快更可靠**，拥有全新的覆盖层和**自动更新启动器**，让你始终使用最新版本。想要最佳性能？请访问 **[fh6sniper.com](https://fh6sniper.com/)**。
>
> <img width="459" height="508" alt="ui-full-preview" src="https://github.com/user-attachments/assets/6428d0f9-47a4-4823-8cb8-aada581304a8" />


---
<img width="1655" height="792" alt="image-3" src="https://github.com/user-attachments/assets/61b58048-c3e6-4156-9510-0c2600aa7e9f" />
<img width="340" height="488" alt="image" src="https://github.com/user-attachments/assets/d594b885-9e5d-4519-bbea-182a3d99999b" />



## Forza Horizon 6 自动拍卖行狙击工具

监视拍卖行中你设定的车辆，一旦出现立即购买，收取车辆并循环。设置好筛选条件后让它自动运行。本工具约有 10% 的购买成功率，通常能在 5 分钟内狙击到一辆车。



---

# 功能特点

- 自动搜索和购买
- 跳过已售列表，寻找新的列表
- 自动收取赢得的所有车辆
- 小巧的置顶覆盖层，显示实时统计数据
- F8 启动/停止，F9 紧急停止
- 达到设定数量或时间后自动停止
- 智能页面识别，防止误点击跳转到其他页面

---

# 支持

如果遇到任何问题需要帮助，欢迎加入支持服务器，在 #Get-Help 中发帖，我会查看。https://discord.gg/PWPmVWdP8r

---

# 系统要求

- Windows 10 或 11
- PC 版 Forza Horizon 6
- 1920 x 1080 分辨率 - 全屏，无上限帧率（可能需要同步修改 Windows 设置）
- 极低画质预设
- 移动背景设置为**开启**（或在配置文件中设置为 false）
- UI 缩放设置为 **100**
- 游戏语言设置为英文
- 键盘菜单导航（机器人使用按键，而非鼠标）
- 如果 Forza 以提升权限启动，你需要以管理员身份运行机器人（右键 + 以管理员身份运行）
- 强烈建议使用有线以太网

<img width="1386" height="763" alt="image-4" src="https://github.com/user-attachments/assets/fd2bf173-259f-4458-938b-2267144ce3ab" />
<img width="1386" height="758" alt="image-5" src="https://github.com/user-attachments/assets/34f3fe88-9575-4ec5-aa6c-0c9e04a9964c" />



---

# 下载

从 [Releases 页面](https://github.com/FrostyIsBored/FH6-Auction-House-Sniper/releases) 获取最新的 **FH6-Sniper.zip**，解压到 PC 上的任意位置。

---

# 设置

## 步骤 1 - 打开拍卖行

启动 Forza Horizon 6，前往嘉年华场地的拍卖行。

<img width="1916" height="971" alt="image-1" src="https://github.com/user-attachments/assets/2e4c412e-974e-4bf4-9d4d-bbc31fcd2432" />

---

## 步骤 2 - 配置搜索条件

打开**搜索拍卖**并设置筛选条件：

- **制造商**和**型号**选择你要的车辆
- **最高直购价**作为安全上限。机器人会直接购买第一辆匹配的车辆，不查看价格，因此这是每辆车你能支付的最高金额。请谨慎设置。

退出到**搜索配置**界面。这就是机器人期望的起始位置。

<img width="1919" height="1079" alt="image" src="https://github.com/user-attachments/assets/7fac68c0-f89d-45ee-a10a-5133b02da681" />

---

## 步骤 3 - 运行狙击工具

双击 **FH6-Sniper.exe**。屏幕左上角会出现一个小覆盖层。

点击回到 FH6，按 **F8** 或点击 **开始**，然后让它自动运行。

若要停止：再次按 **F8**，**F9** 紧急停止，或点击覆盖层上的 **停止**。

<img width="1902" height="1062" alt="image-2" src="https://github.com/user-attachments/assets/ccdfba46-4c90-42de-bb79-fe26658bb262" />

---

# SmartScreen 警告

Windows SmartScreen 会发出警告，因为 exe 未签名。要运行：

1. 点击 **更多信息**
2. 点击 **仍要运行**

---

# 热键

| 按键 | 操作 |
|---|---|
| **F8** | 启动 / 停止 |
| **F9** | 紧急停止 |
| **停止** 按钮 | 与 F8 相同 |
| **✕**（覆盖层） | 关闭并退出 |

---

# 设置

机器人开箱即用。如需调整，打开 **config.json**（首次运行 exe 时创建在 exe 旁边）：

- **max_cars** - 赢得这么多辆车后自动停止（默认：1）
- **max_minutes** - 运行这么多分钟后自动停止（默认：180）
- **collect_after_buyout** - 如果希望手动收取车辆，设为 `false`
- **notify_sound** / **notify_toast** - 关闭成功蜂鸣音或 Windows 通知
- **buyout_select_delay_ms** - 在选择「直购」和按下回车之间的额外延迟（毫秒）。如果机器人偶尔打开「出价」对话框而不是「直购」，可增加到 `200`（默认：0）
- **moving_background** - 如果游戏内关闭了移动背景视频设置，设为 `false`（默认：true）

---

# 重要说明

> [!WARNING]
> - 拍卖行自动化可能违反 Forza 的执行准则。
> - 结果可能因 PC/网络配置而异。
> - 你可能面临警告、暂停或永久封禁的风险。
> - 自行承担使用风险。

---

# 注意事项

- 机器人仅在 FH6 是焦点窗口时运行。切换到其他窗口时覆盖层会显示**已暂停**。点击回到游戏即可恢复。
- 覆盖层会从屏幕捕获中隐藏，因此你可以放在屏幕上的任何位置。
- 点击并按住覆盖层标题栏可拖动。
- 你不会赢得每一次狙击。机器人受限于 FH6 的菜单动画和拍卖服务器响应速度，与其他工具相同。
- 如果服务器缓慢/过载，可能导致机器人出错（将尽快修复）。

---

# 故障排除

**覆盖层显示「已暂停」** - FH6 不是焦点窗口。点击进入游戏。

**F8 无反应** - PC 上可能有其他应用占用了 F8 键。关闭该应用，或在 `config.json` 中更改热键。

**机器人卡在某画面不动** - 重启 FH6 和机器人。确保画质预设为**极低**，分辨率为 **1920 x 1080**。

**狙击工具打开了直购对话框，但不会点击「是」。**
<img width="1513" height="840" alt="image" src="https://github.com/user-attachments/assets/61472f11-389c-47f9-90e3-197530331486" />

几乎总是由于 FH6 的**移动背景**视频设置与狙击工具不匹配。如果你在游戏中关闭了移动背景，打开覆盖层的**设置**选项卡，取消勾选「移动背景模式」，这样狙击工具会加载正确的模板。

<img width="331" height="472" alt="image" src="https://github.com/user-attachments/assets/049c4dab-a718-4cab-882e-d45782f5391c" />

**狙击工具在启动后立即显示「已停止：无法恢复」。**

两种常见原因：

- **游戏语言不是英文。** 狙击工具的模板仅匹配英文界面。在 设置 > 语言选择 中将 FH6 切换为英文。
- **可捕获的覆盖层遮挡了菜单。** 如果你开启了「在截图和录制中显示覆盖层」，覆盖层可能挡在了狙击工具读取的区域上方。将其拖到右上或右下角，使其不重叠游戏 UI。

如果以上方法无效，请[提交 issue](https://github.com/FrostyIsBored/FH6-Auction-House-Sniper/issues) 或在 Discord 上联系我。
**在提交与机器人相关的问题时** - 请附上你的 Sniper.log 文件，以便我查看。
