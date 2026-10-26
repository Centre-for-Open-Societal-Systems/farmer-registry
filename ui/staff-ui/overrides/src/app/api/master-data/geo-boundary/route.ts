import { NextRequest, NextResponse } from "next/server";
import { getBackendConfig } from "@/app/api/_lib/backend-config";
import { createBackendRequest } from "@/app/api/_lib/backend-request";
import { requireAuth } from "@/app/api/_lib/requireAuth";

// A level's boundary GeoJSON from Master Data, which seeds it with the country
// pack's hierarchy (boundaries/<level>.geojson), so every registry draws and
// looks up locations from the same polygons as its location fields.
// GET ?level=<level mnemonic>. Master Data answers with the GeoJSON itself
// (stream), not the usual envelope, so this does not go through proxyToBackend.
export async function GET(req: NextRequest) {
	const auth = requireAuth(req);
	if (auth instanceof NextResponse) return auth;

	const level = req.nextUrl.searchParams.get("level") ?? "";
	if (!/^[A-Za-z0-9_-]{1,64}$/.test(level)) {
		return NextResponse.json({ statusText: "level is required", code: 400 }, { status: 400 });
	}

	const h = req.headers;
	const origin = h.get("origin") || `${h.get("x-forwarded-proto") || "https"}://${h.get("x-forwarded-host") || h.get("host")}`;
	try {
		const response = await fetch(`${getBackendConfig().masterdataBackendApiUrl}/catalogue/get_geo_boundary`, {
			method: "POST",
			headers: { ...auth.backendHeaders, "Content-Type": "application/json" },
			body: JSON.stringify(createBackendRequest({ request_payload: { level, stream: true } }, origin)),
		});
		if (!response.ok || !(response.headers.get("content-type") ?? "").includes("geo+json")) {
			// No boundaries for the level, or a Master Data without the catalogue.
			return NextResponse.json({ statusText: "No boundary for this level", code: 404 }, { status: 404 });
		}
		return new NextResponse(response.body, {
			status: 200,
			headers: { "Content-Type": "application/geo+json", "Cache-Control": "private, max-age=3600" },
		});
	} catch {
		return NextResponse.json({ statusText: "Master Data is not reachable", code: 502 }, { status: 502 });
	}
}
