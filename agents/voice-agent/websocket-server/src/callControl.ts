const { TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN } = process.env;

let callSid: string | undefined;

export function setCallSid(sid: string | undefined) {
  callSid = sid;
}

const authHeader =
  TWILIO_ACCOUNT_SID && TWILIO_AUTH_TOKEN
    ?
        "Basic " +
        Buffer.from(`${TWILIO_ACCOUNT_SID}:${TWILIO_AUTH_TOKEN}`).toString(
          "base64"
        )
    : undefined;

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
