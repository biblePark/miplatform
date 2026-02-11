import type { PreviewScreenProps } from "../../manifest/types";

export default function PlaceholderScreen({ manifestEntry }: PreviewScreenProps) {
  return (
    <article>
      <h2 style={{ marginTop: 0 }}>
        {manifestEntry.title ?? `${manifestEntry.screenId} (placeholder)`}
      </h2>
      <p>
        This placeholder proves that the Preview Host can resolve an entry module
        from the screen manifest and render it under <code>/preview/:screenId</code>.
      </p>
      <ul>
        <li>
          <strong>screenId:</strong> {manifestEntry.screenId}
        </li>
        <li>
          <strong>entryModule:</strong> {manifestEntry.entryModule}
        </li>
        <li>
          <strong>sourceXmlPath:</strong> {manifestEntry.sourceXmlPath}
        </li>
        <li>
          <strong>sourceNodePath:</strong> {manifestEntry.sourceNodePath}
        </li>
      </ul>
    </article>
  );
}
