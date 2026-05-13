import { useTokensStore, type PrincipalKey } from "@/store/tokens";
import { useModeStore } from "@/store/mode";

interface Props {
  principal: PrincipalKey;
  audience: "collectmind-tenant" | "collectmind-operator";
}

const AUDIENCE_LABEL: Record<Props["audience"], string> = {
  "collectmind-tenant": "tenant",
  "collectmind-operator": "operator",
};

export function TokenChip({ principal, audience }: Props) {
  const mode = useModeStore((s) => s.mode);
  const token = useTokensStore((s) => s.tokens[principal]);
  const present = mode === "recorded" || Boolean(token);
  return (
    <div className="flex items-center gap-2 text-xs">
      <span className="text-zinc-500">principal</span>
      <span className="font-mono text-zinc-200">{principal}</span>
      <span className="text-zinc-500">aud</span>
      <span className="font-mono text-zinc-200">{AUDIENCE_LABEL[audience]}</span>
      <span className={present ? "pill-ok" : "pill-bad"}>
        {mode === "recorded" ? "fixture" : present ? "JWT loaded" : "no JWT"}
      </span>
    </div>
  );
}
