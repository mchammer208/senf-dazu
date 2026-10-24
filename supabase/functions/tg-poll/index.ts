// Einsammler: fragt jede Minute bei Telegram nach, quittiert jeden Klick sofort
// und legt ihn in der Tabelle tg_inbox ab.
//
// Hintergrund: Telegram hält einen Knopfdruck nur kurz vor. Wer erst alle zehn
// Minuten nachsieht, findet ihn womöglich nicht mehr. Dieser Dienst holt ihn
// binnen einer Minute ab – die eigentliche Arbeit macht weiter der Zehn-Minuten-Lauf.

const BASIS = Deno.env.get("SUPABASE_URL")!;
const KEY = Deno.env.get("SUPABASE_SERVICE_ROLE_KEY")!;
const KOPF = { apikey: KEY, Authorization: `Bearer ${KEY}`, "Content-Type": "application/json" };

async function rest(pfad: string, init: RequestInit = {}) {
  const r = await fetch(`${BASIS}/rest/v1/${pfad}`, {
    ...init,
    headers: { ...KOPF, ...(init.headers ?? {}) },
  });
  const text = await r.text();
  if (!r.ok) throw new Error(`${pfad}: HTTP ${r.status} ${text.slice(0, 200)}`);
  return text ? JSON.parse(text) : null;
}

Deno.serve(async () => {
  try {
    const geheim = await rest("geheimnisse?key=eq.telegram_token&select=value");
    const token = (geheim?.[0]?.value ?? "").trim();
    if (!token) {
      return Response.json({ fehler: "Kein telegram_token in der Tabelle geheimnisse" }, { status: 500 });
    }
    const api = `https://api.telegram.org/bot${token}`;

    const gespeichert = await rest("settings?key=eq.tg_offset&select=value");
    let offset = Number(gespeichert?.[0]?.value ?? 0) || 0;

    const antwort = await fetch(`${api}/getUpdates?offset=${offset}&timeout=0`);
    const daten = await antwort.json();
    if (!daten?.ok) {
      return Response.json({ fehler: "Telegram antwortet nicht ok", daten }, { status: 502 });
    }
    const updates: Array<Record<string, unknown>> = daten.result ?? [];

    let abgelegt = 0;
    for (const u of updates) {
      const id = u.update_id as number;
      offset = id + 1;

      try {
        await rest("tg_inbox", {
          method: "POST",
          headers: { Prefer: "resolution=ignore-duplicates,return=minimal" },
          body: JSON.stringify({ update_id: id, payload: u }),
        });
        abgelegt++;
      } catch (e) {
        console.error("Ablegen fehlgeschlagen", id, String(e));
      }

      // Sofort quittieren, damit der Kreisel am Knopf verschwindet und Telegram
      // den Klick nicht als unbeantwortet verwirft.
      const cq = u.callback_query as { id?: string } | undefined;
      if (cq?.id) {
        await fetch(`${api}/answerCallbackQuery`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ callback_query_id: cq.id, text: "Angekommen – wird gleich erledigt." }),
        }).catch((e) => console.error("Quittieren fehlgeschlagen", String(e)));
      }
    }

    if (updates.length) {
      await rest("settings?key=eq.tg_offset", {
        method: "PATCH",
        headers: { Prefer: "return=minimal" },
        body: JSON.stringify({ value: String(offset), updated_at: new Date().toISOString() }),
      });
    }

    return Response.json({ abgeholt: updates.length, abgelegt, offset });
  } catch (e) {
    console.error(String(e));
    return Response.json({ fehler: String(e) }, { status: 500 });
  }
});
