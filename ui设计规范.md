这是为您定制的 **ainovel "Atelier" (工坊) 设计系统与全栈开发规范书 v1.1**。

这份文档将作为您毕业设计的“UI/UX圣经”。它不仅仅是关于美观，更是为了让评委老师一眼看到“专业度”和“差异化”。

---

# 📖 ainovel 开发规范书：Project Atelier

> **设计愿景**：这不是一个“生成器”，而是一个“数字化书房”。
> **核心隐喻**：纸张、墨水、自然光、呼吸感。
> **对标产品**：
> *   **整体质感**：[Typefully](https://typefully.com/) (极致的专注写作体验)
> *   **配色与温润感**：[Claude.ai](https://claude.ai/) (暖色背景，非侵入式AI)
> *   **组件交互细节**：[Linear](https://linear.app/) (虽然它是黑色的，但请参考它的边框处理、微交互和紧凑感)
> *   **排版美学**：[Ghost](https://ghost.org/) (现代出版风格)

---

## 1. 视觉设计语言 (Visual Design Language)

### 1.1 色彩系统：The "Paper & Ink" Palette

抛弃纯黑纯白，使用**高高级感的“暖灰”与“陶土”体系**。

**Light Mode (默认 - 日间书房)**
*   **画布背景 (Canvas)**: `bg-[#FBF9F6]` (暖米白，像道林纸)
*   **侧边栏/卡片 (Surface)**: `bg-[#F2EFE9]` (稍深的暖灰，区分层级)
*   **主文字 (Ink)**: `text-[#2C2926]` (深炭灰，柔和不刺眼)
*   **次要文字**: `text-[#6E6A66]` (石灰色)
*   **边框**: `border-[#E6E2DC]` (极淡的铅笔痕迹)
*   **主色调 (Accent)**: `text-[#BC5D43]` (陶土红 - 用于按钮/高亮/链接)
    *   *辅助色*: `#3F6359` (松石绿 - 用于成功/完成状态)

**Dark Mode (夜间书房)**
*   **画布背景**: `bg-[#1A1918]` (深咖啡黑，不是纯黑)
*   **侧边栏/卡片**: `bg-[#242321]`
*   **文字**: `text-[#E8E6E3]` (暖灰白)
*   **主色调**: `text-[#D97757]` (提亮的陶土色)

### 1.2 排版系统 (Typography)

*   **UI 字体 (导航/菜单)**: `Inter` 或 `Geist Sans` (清晰、现代、中性)
*   **内容字体 (大纲/正文)**: `Merriweather` 或 `Source Serif 4` (衬线体，书卷气核心)
    *   *正文设置*: 字号 `17px`，行高 `1.75`，字间距 `tracking-tight` (-0.01em)。
*   **代码/Prompt**: `JetBrains Mono` 或 `Fira Code` (暗示“工坊”的技术属性)。

### 1.3 阴影与圆角
*   **圆角**: 统一 `rounded-lg` (8px) 或 `rounded-xl` (12px)。拒绝全圆角 (Pill)。
*   **阴影**:
    *   `shadow-sm`: `0 1px 2px 0 rgb(0 0 0 / 0.05)` (卡片默认)
    *   `shadow-float`: `0 10px 30px -10px rgba(44, 41, 38, 0.08)` (悬浮面板/模态框)

---

## 2. 页面布局规划 (Page Layouts)

### 2.1 核心布局结构 (The App Shell)

所有页面共享一个外壳，采用 **"双栏布局" (Sidebar + Main Content)**。

*   **侧边栏 (Sidebar)**:
    *   **宽度**: 固定 `260px`。
    *   **位置**: 左侧固定。
    *   **样式**: 背景色为 `Surface`，右侧有一条极细的边框。
    *   **内容**: 项目列表、设置入口、当前项目的导航树 (设定/大纲/章节)。
    *   **交互**: 可收起 (Collapse)，收起后变成图标栏 (56px)。

*   **主内容区 (Main Content)**:
    *   **宽度**: `flex-1` (自适应剩余空间)。
    *   **容器**: 内部通常包含一个 `max-w-4xl` (约 900px) 的居中容器，模拟“桌子上的纸张”。
    *   **Padding**: 上下左右至少 `32px` 的留白。

### 2.2 关键页面线框 (Wireframes)

#### A. Dashboard (项目概览)
*   **布局**: 网格布局 (Grid)。
*   **元素**:
    *   顶部: "下午好，作者" (大号衬线标题)。
    *   中部: "最近编辑" 卡片组。每个卡片像一本书的封面，带有陶土色进度条。
    *   新建按钮: 一个虚线边框的空卡片，中心是 "+" 号。

#### B. 写作工作台 (The Workspace) - **MVP 核心**
这是一个 Tab 切换式页面，保持上下文不中断。

1.  **Tab: 设定 (Settings)**
    *   左侧: 设定目录 (世界观/人物/大纲)。
    *   右侧: 表单区域。输入框不要用标准 Input，要用 **"下划线式"** (Underline Input) 或 **"极简块"** (Minimal Block)，像填空题一样。

2.  **Tab: 章节写作 (Writing)**
    *   **三列模式 (可选)**: 
        *   最左: 章节列表 (200px)。
        *   中间: 写作白板 (A4纸质感，居中，阴影)。
        *   最右 (可折叠): AI 助手/素材库 (300px)。
    *   **AI 助手面板**: 
        *   不要做成聊天窗口！
        *   做成 **"批注卡片" (Annotation Cards)**。你选中一段文本，AI 在右侧弹出一张卡片给出建议。
        *   生成按钮放在编辑器选中文本后的 **悬浮工具栏 (Floating Toolbar)** 上，类似 Notion 的 "/" 命令或 Medium 的选中菜单。

---

## 3. 组件开发规范 (Component Specs)

使用 `shadcn/ui` 作为底座，但必须进行 **"去默认化"** 定制。

### 3.1 按钮 (Button)
*   **主要按钮 (Primary)**: 
    *   Class: `bg-[#BC5D43] hover:bg-[#A34B35] text-white shadow-sm rounded-lg font-medium tracking-wide`
    *   动效: `active:scale-95 transition-all duration-200`
*   **次要按钮 (Ghost)**:
    *   Class: `hover:bg-[#E6E2DC] text-[#57534E] hover:text-[#2C2926]`
*   **AI 魔法按钮**:
    *   加一个微弱的 `ring` 光晕，图标使用 ✨。

### 3.2 输入框 (Input / Textarea)
*   **风格**: 去掉四周的灰色边框，只保留底部边框，或者使用极淡的背景色填充。
*   **Focus 状态**: 底部边框变为陶土色，无蓝色光圈 (Ring)。
*   **代码示例**:
    ```jsx
    // 这是一个 "Atelier" 风格的 Input
    <input className="bg-transparent border-b border-[#E6E2DC] focus:border-[#BC5D43] outline-none px-0 py-2 transition-colors placeholder:text-[#A8A29E]" />
    ```

### 3.3 卡片 (Card)
*   **风格**: 白色 (Light mode) 或 深灰 (Dark mode) 背景，极细边框，微弱阴影。
*   **Class**: `bg-white dark:bg-[#242321] border border-[#E6E2DC] rounded-xl shadow-[0_2px_8px_rgba(0,0,0,0.04)]`

---

## 4. 交互与动效规范 (Interaction & Motion)

本项目动效目标是「**视觉连续性**」：用户能感到“顺滑”，但不应明显意识到“在做动画”。

**总原则**：统一使用可控的时间曲线（Cubic Bezier），避免不可预测的弹簧物理；所有可交互元素必须具备 `Hover / Focus / Active / Disabled` 的完整状态闭环。

实现上以 **CSS Transition（轻量、默认）** + **Framer Motion（需要布局投影/交错/Presence 时）** 为主。

### 4.0 动效 Token（必须全局统一）

> 把数字“锁死在 Token 里”，页面/组件不得随意写散的 `duration/ease`（除非有明确例外与注释）。

**标准缓动（默认）**
- `easeStandard`: `cubic-bezier(0.25, 0.1, 0.25, 1)`（类 iOS 的自然感）

**黄金时间窗口**
- `durationFast`: 150ms（Hover / 微小反馈）
- `durationBase`: 250ms（默认交互过渡）
- `durationSlow`: 350ms（模态/抽屉/大块 UI）
- `durationStagger`: 30ms（列表/网格交错间隔）

**空间与力度**
- `fadeUpDistance`: 10px（页面/面板入场上浮）
- `pressScale`: 0.98（按压确认感）

**无障碍**
- 遵循 `prefers-reduced-motion`：在“减少动态效果”下，所有动画应降级为几乎瞬时（或只保留淡入淡出）。

### 4.1 页面转场 (Page Transition)
页面路由切换采用 **“原地叠化”**：
- **新页面**在当前视图之上入场：`opacity 0→1` + `y: +10px→0`
- **旧页面**保持静止（或极微弱后退，但禁止大幅横向滑动造成眩晕）
- 建议 `duration: 280–320ms` + `easeStandard`

### 4.2 AI 生成动效 (The "Ghostwriter" Effect)
当 AI 生成内容时：
1.  不要一次性显示全部。
2.  不要用打字机效果（太慢）。
3.  **推荐**: **流式渐显 (Stream Fade)**。新生成的文本块带有一个 `opacity: 0 -> 1` 的过渡，像墨水渗入纸张。

### 4.3 按钮与可点击元素（Pressable）
所有按钮/可点击卡片/可点击列表项必须具备：
- **Hover**：仅做背景色亮度平滑过渡（`durationFast`），可选极淡阴影扩散（禁止夸张“浮起”）
- **Active**：`scale: pressScale`（按下即缩放，松开平滑复原；禁止弹簧回弹）
- **Focus（键盘）**：`focus-visible` 的陶土色柔和外圈（无蓝色默认 Ring）
- **Disabled**：降低对比度与点击感知（`opacity` + `cursor: not-allowed`）

> 规则：**只要能点击，鼠标悬浮就必须有反馈**（哪怕是 1% 的背景色变化）。

### 4.4 输入框 / Textarea / Prompt 编辑区
输入类控件必须具备：
- **Focus 过渡**：边框/下划线颜色改变必须带动画（`durationFast`/`durationBase`）
- **Focus-within**：若输入控件被包在卡片/分组里，分组容器应在聚焦时呈现轻微强调（边框/背景微变）
- **Placeholder 策略**：优先“Label 常驻”，若使用 Placeholder 作为 Label，则应采用平滑缩小上移的浮动标签（而非直接消失）
- **插入/流式文本**：新增文本块以轻微淡入呈现（墨水渗入纸张），避免突兀跳变

### 4.5 列表 / 网格 / 大纲加载
对任何“列表/网格”首次渲染与刷新都应用：
- **交错（Stagger）**：子元素按 `durationStagger` 依次 `fade+up` 入场，形成秩序感
- **布局变化**：新增/删除/排序应尽量使用“布局动画”消除视线跳动

### 4.6 Toast（右下角通知）
Toast 必须满足：
- **出现/消失**：`opacity` + `y` 微动（`durationBase`）
- **堆叠与重排**：增加/删除触发布局重排动画，其余消息平滑位移填补空缺
- **背景质感**：可使用 `backdrop-blur` 的渐变（避免突然出现的硬边）

### 4.7 侧边栏折叠 / Tab 切换 / 选中态高亮
- 侧边栏折叠：主内容区应平滑挤压/展开（禁止跳变）
- Tab/导航选中态：高亮背景块使用 **布局投影（Layout Projection）** 在选项间平滑滑动变形（而非生硬显隐）

### 4.8 长列表滚动加载（Skeleton）
对长列表/懒加载：
- 新内容出现前预留骨架屏占位（呼吸渐变）
- 内容加载完成后 `opacity fade-in` 平滑替换骨架屏
- 禁止高度突变导致视线跳动

---

## 5. 开发落地指南 (Implementation Roadmap)

### 5.1 技术栈配置
1.  **前端**: React (Vite) + TypeScript
2.  **样式**: Tailwind CSS
3.  **组件**: Shadcn/ui (Radix Primitives)
4.  **图标**: Lucide React
5.  **动画**: Framer Motion
6.  **编辑器**: Tiptap (Headless 富文本编辑器，比 Markdown 更容易做自定义 UI) **或者** 简单的 React Markdown Editor (MVP 推荐)。

### 5.2 目录结构建议
```text
src/
├── components/
│   ├── ui/           # Shadcn 基础组件 (Button, Input...)
│   ├── atelier/      # 定制化业务组件
│   │   ├── ProjectCard.tsx
│   │   ├── ChapterEditor.tsx
│   │   └── AIPromptPanel.tsx
│   └── layout/       # AppShell, Sidebar
├── lib/
│   ├── theme.ts      # 颜色变量定义
│   └── utils.ts
├── pages/            # 路由页面
├── styles/
│   └── globals.css   # Tailwind CSS 变量配置
└── App.tsx
```

### 5.3 Tailwind 配置 (`tailwind.config.js`)
把设计规范锁死在配置里：

```javascript
export default {
  theme: {
    extend: {
      colors: {
        background: "var(--background)",
        foreground: "var(--foreground)",
        primary: {
          DEFAULT: "#BC5D43", // 陶土色
          foreground: "#FFFFFF",
        },
        paper: "#FBF9F6", // 纸张背景
        surface: "#F2EFE9", // 侧边栏背景
      },
      fontFamily: {
        sans: ["Geist Sans", "Inter", "sans-serif"],
        serif: ["Merriweather", "serif"], // 关键！
      }
    }
  }
}
```

### 5.4 快速启动代码 (CSS Variables)
在 `globals.css` 中定义你的书房氛围：

```css
@layer base {
  :root {
    --background: 40 20% 97%; /* #FBF9F6 */
    --foreground: 30 5% 15%;  /* #2C2926 */
    --primary: 12 48% 50%;    /* #BC5D43 */
    --border: 35 10% 88%;     /* #E6E2DC */
    --radius: 0.75rem;
  }
  .dark {
    --background: 30 5% 10%;  /* #1A1918 */
    --foreground: 35 5% 90%;
    --border: 30 5% 20%;
  }
}

/* 让所有编辑器区域自动应用衬线体 */
.editor-content {
  font-family: 'Merriweather', serif;
  line-height: 1.8;
  font-size: 1.1rem;
}
```

---

## 6. 验收标准 checklist

在提交毕业设计前，请对照此表自查：

1.  [ ] **字体检查**：正文是否一定是衬线体？UI 是否是无衬线体？
2.  [ ] **颜色检查**：界面里是否还有纯黑 (#000) 或纯白 (#FFF)？如果有，替换掉。
3.  [ ] **呼吸感**：内容距离屏幕边缘是否有足够的留白（Padding）？
4.  [ ] **动效**：切换页面时是否平滑？按钮点击是否有反馈？
5.  [ ] **一致性**：所有 Input/Button/卡片/列表项是否统一使用动效 Token（禁止散写）？
6.  [ ] **可交互反馈**：所有可点击/可聚焦元素是否都有 Hover/Focus/Active 状态？
7.  [ ] **布局连续性**：Toast 堆叠、Tab 高亮、列表增删是否有平滑位移？
8.  [ ] **加载体验**：长列表/关键页面是否有 Skeleton 与平滑替换，避免跳动？

这套规范能保证你做出来的 MVP 不像一个 CRUD 后台管理系统，而像一个精心打磨的商业级写作软件。祝开发顺利！
