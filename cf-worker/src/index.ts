import * as PostalMime from "postal-mime";

const ENDPOINT = "https://email-polling.hwemite.lol";

interface EmailMessage {
  readonly from: string;
  readonly to: string;
}

interface ForwardableEmailMessage<Body = unknown> {
  readonly from: string;
  readonly to: string;
  readonly headers: Headers;
  readonly raw: ReadableStream;
  readonly rawSize: number;

  setReject(reason: string): void;
  forward(rcptTo: string, headers?: Headers): Promise<void>;
  reply(message: EmailMessage): Promise<void>;
}

export default {
  async email(message: ForwardableEmailMessage, env: object, ctx: object) {
    const parser = new PostalMime.default();
    const rawEmail = new Response(message.raw);
    const email = await parser.parse(await rawEmail.arrayBuffer());
    const payload = {
      content: email.html,
      from: message.from,
      to: message.to,
    };
    const response = await fetch(ENDPOINT, {
      method: "POST",
      headers: {
        "content-type": "application/json",
      },
      body: JSON.stringify(payload),
    });

    if (!response.ok) {
      const body = await response.text().catch(() => "");
      throw new Error(
        `Failed to POST payload: ${response.status} ${response.statusText} ${body}`,
      );
    }
  },
};
