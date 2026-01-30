import { useParams } from "react-router-dom";

import { DebugDetails, DebugPageShell } from "../components/atelier/DebugPageShell";
import { TablesPanelInline } from "../components/writing/TablesPanel";
import { UI_COPY } from "../lib/uiCopy";

export function NumericTablesPage() {
  const { projectId } = useParams();

  if (!projectId) return <div className="text-subtext">缺少 projectId</div>;

  return (
    <DebugPageShell
      title={UI_COPY.nav.numericTables}
      description="数值表格系统：用于管理可数字化的结构化状态（例如金钱/时间/等级/资源等）。"
    >
      <DebugDetails title="说明">
        <div className="grid gap-1 text-xs text-subtext">
          <div>本页为“数值表格系统”的 AdvancedDebug；与“图谱数据（StructuredMemory）”分离。</div>
          <div>支持直接编辑表与行（project_tables / project_table_rows）。</div>
        </div>
      </DebugDetails>

      <TablesPanelInline projectId={projectId} />
    </DebugPageShell>
  );
}
