import { useState } from "react";
import { useParams } from "react-router-dom";

import { DebugDetails, DebugPageShell } from "../components/atelier/DebugPageShell";
import { TablesPanel } from "../components/writing/TablesPanel";
import { UI_COPY } from "../lib/uiCopy";

export function NumericTablesPage() {
  const { projectId } = useParams();
  const [open, setOpen] = useState(false);

  if (!projectId) return <div className="text-subtext">缺少 projectId</div>;

  return (
    <>
      <DebugPageShell
        title={UI_COPY.nav.numericTables}
        description="数值表格系统：用于管理可数字化的结构化状态（例如金钱/时间/等级/资源等）。"
        actions={
          <button className="btn btn-primary" type="button" onClick={() => setOpen(true)} aria-label="numeric_tables_open">
            打开表格面板
          </button>
        }
      >
        <DebugDetails title="说明">
          <div className="grid gap-1 text-xs text-subtext">
            <div>本页是“数值表格系统”的入口；与“图谱数据（StructuredMemory）”分离。</div>
            <div>当前复用写作页的 TablesPanel；后续会补全更完整的 AdvancedDebug 视图。</div>
          </div>
        </DebugDetails>

        <div className="panel p-4 text-sm text-subtext">点击右上角“打开表格面板”开始。</div>
      </DebugPageShell>

      <TablesPanel open={open} onClose={() => setOpen(false)} projectId={projectId} />
    </>
  );
}

