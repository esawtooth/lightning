const { TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN, PUBLIC_URL, TWILIO_FROM_NUMBER } =
  process.env;

let callSid: string | undefined;

export function setCallSid(sid: string | undefined) {
  callSid = sid;
}

export function getCallSid(): string | undefined {
  return callSid;
}

const authHeader =
  TWILIO_ACCOUNT_SID && TWILIO_AUTH_TOKEN
    ?
        "Basic " +
        Buffer.from(`${TWILIO_ACCOUNT_SID}:${TWILIO_AUTH_TOKEN}`).toString(
          "base64"
        )
    : undefined;

export async function startCall(to: string) {
  if (!authHeader) throw new Error("Twilio client not configured");
  if (!TWILIO_FROM_NUMBER) throw new Error("TWILIO_FROM_NUMBER not set");
  if (!PUBLIC_URL) throw new Error("PUBLIC_URL not set");

  const url = `https://api.twilio.com/2010-04-01/Accounts/${TWILIO_ACCOUNT_SID}/Calls.json`;
  const voiceUrl = `${PUBLIC_URL}/twiml`;
  const res = await fetch(url, {
    method: "POST",
    headers: {
      Authorization: authHeader,
      "Content-Type": "application/x-www-form-urlencoded",
    },
    body: new URLSearchParams({
      From: TWILIO_FROM_NUMBER,
      To: to,
      Url: voiceUrl,
    }).toString(),
  });
  if (!res.ok) {
    const text = await res.text();
    throw new Error(`Twilio error: ${res.status} ${text}`);
  }
  const data = await res.json();
  callSid = data.sid;
  return { status: "calling", sid: data.sid };
}

export async function sendDigits(digits: string) {
  if (!authHeader) throw new Error("Twilio client not configured");
  if (!callSid) throw new Error("No active call to send digits");
  const url = `https://api.twilio.com/2010-04-01/Accounts/${TWILIO_ACCOUNT_SID}/Calls/${callSid}/Play.json`;
  const res = await fetch(url, {
    method: "POST",
    headers: {
      Authorization: authHeader,
      "Content-Type": "application/x-www-form-urlencoded",
    },
    body: new URLSearchParams({ Digits: digits }).toString(),
  });
  if (!res.ok) {
    const text = await res.text();
    throw new Error(`Twilio error: ${res.status} ${text}`);
  }
  return { status: "sent", digits };
}
