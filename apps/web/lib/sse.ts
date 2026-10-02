import { authFetch, toApiError } from "@/lib/api";

export interface SseEvent {
  event: string;
  data: string;
}

/**
 * Lee un stream Server-Sent Events con fetch.
 * Se usa en lugar de EventSource porque este no permite enviar el header Authorization
 * ni hacer POST.
 */
export async function* streamSse(
  path: string,
  init: RequestInit = {},
): AsyncGenerator<SseEvent> {
  const response = await authFetch(path, {
    ...init,
    headers: { Accept: "text/event-stream", ...init.headers },
  });
  if (!response.ok || !response.body) throw await toApiError(response);

  const reader = response.body.pipeThrough(new TextDecoderStream()).getReader();
  let buffer = "";
  while (true) {
    const { value, done } = await reader.read();
    if (done) break;
    buffer += value.replace(/\r\n/g, "\n");
    let boundary = buffer.indexOf("\n\n");
    while (boundary !== -1) {
      const block = buffer.slice(0, boundary);
      buffer = buffer.slice(boundary + 2);
      boundary = buffer.indexOf("\n\n");

      let event = "message";
      const data: string[] = [];
      for (const line of block.split("\n")) {
        if (line.startsWith("event:")) event = line.slice(6).trim();
        else if (line.startsWith("data:")) data.push(line.slice(5).replace(/^ /, ""));
      }
      if (data.length) yield { event, data: data.join("\n") };
    }
  }
}
