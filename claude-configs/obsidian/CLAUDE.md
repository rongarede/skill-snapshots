# Obsidian 库管理规则

## 方法论：PARA + AMOC

### 1. 文件组织 (PARA)
- **项目 (`100_Projects/`)**: 按项目名称分组。项目完成后，将其移动至 `400_Archives/`。
- **领域 (`200_Areas/`)**: 按长期关注的领域分组（例如：`Area_区块链`、`Area_AI`）。
- **资源 (`300_Resources/`)**: `Zettelkasten/` 存放原子化笔记，`Assets/` 存放附件，其他文件夹存放工具或代码片段。
- **收件箱 (`000_Inbox/`)**: 用于快速捕获灵感或临时笔记。

### 2. 逻辑结构 (AMOC)
- **强制属性**: 每一篇新笔记 **必须** 在 YAML Frontmatter 或行内字段中包含 `up:: "[[Parent_MOC]]"` 属性。
- **MOC 创建**: 每个重要的子文件夹都应包含一个 `_xxx_moc.md` 文件作为其逻辑索引。
- **Dataview 代码片段**: 在 MOC 文件中使用以下代码列出子笔记：
  ```dataview
  TABLE file.ctime AS "创建时间", status AS "状态"
  FROM ""
  WHERE contains(up, this.file.link)
  SORT file.ctime DESC
  ```

## 工作标准
- **模板使用**: 创建新笔记时，始终使用 `300_Resources/Templates/` 目录下的模板。
- **命名规范**: MOC 文件应以下划线开头（例如：`_blockchain_moc.md`）。
- **归档流程**: 定期检查 `100_Projects/`，将已完成的项目移动至 `400_Archives/`。
- **结构一致性**: 确保 `up::` 属性严格指向有效的 MOC，以维持自动索引链条的完整性。