import "jsr:@supabase/functions-js/edge-runtime.d.ts";
import { createClient } from "https://esm.sh/@supabase/supabase-js@2";

const POSTMARK_SERVER_TOKEN =
  Deno.env.get("POSTMARK_SERVER_TOKEN") ??
  "fa7edd94-5dc2-49f3-b07e-52132ff16bb9";
const POSTMARK_FROM = "naodasfaw22@augustana.edu";
const SUPABASE_URL = Deno.env.get("SUPABASE_URL") ?? "";
const SUPABASE_SERVICE_ROLE_KEY = Deno.env.get("SUPABASE_SERVICE_ROLE_KEY") ?? "";

const VALID_TYPES = ["intake_confirmation", "conflict_clear", "engagement_signed"] as const;
type EmailType = (typeof VALID_TYPES)[number];

function buildEmail(emailType: EmailType, recipientName: string, matterType: string) {
  const name = recipientName || "Client";
  const typeLabel = matterType || "your matter";

  if (emailType === "intake_confirmation") {
    return {
      subject: `We received your ${typeLabel} submission`,
      textBody:
        `Dear ${name},\n\n` +
        `We received your submission for ${typeLabel}. An attorney will review it shortly.\n\n` +
        `Thank you.`,
      htmlBody:
        `<p>Dear ${name},</p>` +
        `<p>We received your submission for <strong>${typeLabel}</strong>. An attorney will review it shortly.</p>` +
        `<p>Thank you.</p>`,
    };
  }

  if (emailType === "conflict_clear") {
    return {
      subject: "Your matter is moving forward",
      textBody:
        `Dear ${name},\n\n` +
        `Your matter is moving forward.\n\n` +
        `Thank you.`,
      htmlBody:
        `<p>Dear ${name},</p>` +
        `<p>Your matter is moving forward.</p>` +
        `<p>Thank you.</p>`,
    };
  }

  return {
    subject: "Your engagement letter has been signed",
    textBody:
      `Dear ${name},\n\n` +
      `Your engagement letter has been signed and your matter is now active.\n\n` +
      `Thank you.`,
    htmlBody:
      `<p>Dear ${name},</p>` +
      `<p>Your engagement letter has been signed and your matter is now active.</p>` +
      `<p>Thank you.</p>`,
  };
}

function jsonResponse(body: Record<string, unknown>, status = 200) {
  return new Response(JSON.stringify(body), {
    status,
    headers: {
      "Content-Type": "application/json",
      "Access-Control-Allow-Origin": "*",
    },
  });
}

Deno.serve(async (req: Request) => {
  if (req.method === "OPTIONS") {
    return new Response(null, {
      status: 204,
      headers: {
        "Access-Control-Allow-Origin": "*",
        "Access-Control-Allow-Methods": "POST, OPTIONS",
        "Access-Control-Allow-Headers": "authorization, x-client-info, apikey, content-type",
      },
    });
  }

  try {
    const {
      matter_id,
      email_type,
      recipient_email,
      recipient_name,
      matter_type,
    } = await req.json();

    if (!matter_id || !email_type || !recipient_email) {
      return jsonResponse({ error: "Missing required fields" }, 400);
    }

    if (!VALID_TYPES.includes(email_type)) {
      return jsonResponse({ error: "Invalid email_type" }, 400);
    }

    if (!POSTMARK_SERVER_TOKEN) {
      return jsonResponse({ error: "POSTMARK_SERVER_TOKEN not configured" }, 500);
    }

    const supabase = createClient(SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY);

    const { data: existing } = await supabase
      .from("email_log")
      .select("id")
      .eq("matter_id", matter_id)
      .eq("email_type", email_type)
      .limit(1)
      .maybeSingle();

    if (existing) {
      return jsonResponse({ already_sent: true });
    }

    const { subject, textBody, htmlBody } = buildEmail(
      email_type as EmailType,
      recipient_name || "",
      matter_type || "",
    );

    const pmRes = await fetch("https://api.postmarkapp.com/email", {
      method: "POST",
      headers: {
        Accept: "application/json",
        "Content-Type": "application/json",
        "X-Postmark-Server-Token": POSTMARK_SERVER_TOKEN,
      },
      body: JSON.stringify({
        From: POSTMARK_FROM,
        To: recipient_email,
        Subject: subject,
        TextBody: textBody,
        HtmlBody: htmlBody,
        MessageStream: "outbound",
      }),
    });

    const pmBody = await pmRes.json();

    if (!pmRes.ok) {
      const errMsg = pmBody?.Message || JSON.stringify(pmBody);
      return jsonResponse({ error: errMsg }, pmRes.status);
    }

    const { error: logErr } = await supabase.from("email_log").insert({
      matter_id,
      email_type,
    });

    if (logErr) {
      return jsonResponse({ error: logErr.message }, 500);
    }

    return jsonResponse({ sent: true });
  } catch (err) {
    return jsonResponse({ error: (err as Error).message }, 500);
  }
});
