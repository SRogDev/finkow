import { AssetInspectorClient } from "@/components/inspector";

export default async function AssetPage({ params }: { params: Promise<{ symbol: string }> }) {
  const { symbol } = await params;
  const clean = decodeURIComponent(symbol).toUpperCase().trim();

  return (
    <div className="flex flex-col gap-6">
      <div>
        <h1 className="text-3xl font-bold tracking-tight">{clean || "Asset"}</h1>
        <p className="mt-1 text-muted-foreground">
          Live quote, your position, and virtual trading for {clean}.
        </p>
      </div>
      <AssetInspectorClient symbol={clean} />
    </div>
  );
}
