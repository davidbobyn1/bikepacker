import { useEffect, useState } from "react";
import { Sun, CloudRain, Cloud, Wind, Thermometer } from "lucide-react";

interface DayForecast {
  date: string;
  dayLabel: string;
  tempMax: number;
  tempMin: number;
  precipPct: number;
  windMax: number;
  code: number; // WMO weather code
}

interface WeatherStripProps {
  lat: number;
  lon: number;
  days: number; // number of trip days (capped at 16)
}

function getWeatherIcon(code: number): React.ReactNode {
  // WMO codes: 0=clear, 1-3=partly cloudy, 51-67=rain, 71-77=snow, 80-82=showers, 95-99=storm
  if (code === 0) return <Sun className="w-5 h-5 text-amber-500" />;
  if (code <= 3) return <Cloud className="w-5 h-5 text-slate-400" />;
  if (code >= 51 && code <= 82) return <CloudRain className="w-5 h-5 text-blue-400" />;
  if (code >= 95) return <Wind className="w-5 h-5 text-slate-500" />;
  return <Cloud className="w-5 h-5 text-slate-400" />;
}

function getWeatherLabel(code: number): string {
  if (code === 0) return "Clear";
  if (code <= 3) return "Partly cloudy";
  if (code <= 48) return "Foggy";
  if (code <= 67) return "Rain";
  if (code <= 77) return "Snow";
  if (code <= 82) return "Showers";
  return "Stormy";
}

function SkeletonCard() {
  return (
    <div className="flex-shrink-0 w-24 bg-secondary/40 rounded-xl p-3 space-y-2 animate-pulse">
      <div className="h-3 bg-muted rounded w-10" />
      <div className="h-5 w-5 bg-muted rounded-full" />
      <div className="h-3 bg-muted rounded w-14" />
      <div className="h-3 bg-muted rounded w-10" />
    </div>
  );
}

export default function WeatherStrip({ lat, lon, days }: WeatherStripProps) {
  const [forecasts, setForecasts] = useState<DayForecast[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const cappedDays = Math.min(days, 16);

  useEffect(() => {
    if (!lat || !lon) return;

    const url =
      `https://api.open-meteo.com/v1/forecast` +
      `?latitude=${lat}&longitude=${lon}` +
      `&daily=temperature_2m_max,temperature_2m_min,precipitation_probability_max,wind_speed_10m_max,weather_code` +
      `&timezone=auto&forecast_days=${cappedDays}`;

    setLoading(true);
    setError(null);

    fetch(url)
      .then((r) => {
        if (!r.ok) throw new Error(`HTTP ${r.status}`);
        return r.json();
      })
      .then((data) => {
        const d = data.daily;
        const parsed: DayForecast[] = d.time.map((date: string, i: number) => {
          const dt = new Date(date);
          const dayLabel = i === 0 ? "Today" : dt.toLocaleDateString("en-US", { weekday: "short", month: "short", day: "numeric" });
          return {
            date,
            dayLabel,
            tempMax: Math.round(d.temperature_2m_max[i]),
            tempMin: Math.round(d.temperature_2m_min[i]),
            precipPct: Math.round(d.precipitation_probability_max[i] ?? 0),
            windMax: Math.round(d.wind_speed_10m_max[i]),
            code: d.weather_code[i],
          };
        });
        setForecasts(parsed);
        setLoading(false);
      })
      .catch((err) => {
        console.error("[WeatherStrip] Failed to fetch forecast:", err);
        setError("Forecast unavailable");
        setLoading(false);
      });
  }, [lat, lon, cappedDays]);

  return (
    <div className="space-y-2">
      <div className="flex items-center justify-between">
        <h4 className="text-xs font-semibold text-muted-foreground uppercase tracking-wider flex items-center gap-1.5">
          <Thermometer className="w-3.5 h-3.5" /> Weather Forecast
        </h4>
        {days > 16 && (
          <span className="text-[10px] text-muted-foreground italic">Forecast available for first 16 days</span>
        )}
      </div>

      {error ? (
        <p className="text-xs text-muted-foreground italic">{error} — check conditions before you ride.</p>
      ) : (
        <div className="flex gap-2 overflow-x-auto pb-1 -mx-1 px-1">
          {loading
            ? Array.from({ length: cappedDays }).map((_, i) => <SkeletonCard key={i} />)
            : forecasts.map((f, i) => (
                <div
                  key={f.date}
                  className="flex-shrink-0 w-24 bg-secondary/40 border border-border rounded-xl p-3 space-y-1.5"
                >
                  <div className="text-[10px] font-medium text-muted-foreground truncate">
                    {i < days ? `Day ${i + 1}` : f.dayLabel}
                  </div>
                  <div className="flex items-center gap-1">
                    {getWeatherIcon(f.code)}
                    <span className="text-[10px] text-muted-foreground">{getWeatherLabel(f.code)}</span>
                  </div>
                  <div className="text-xs font-semibold text-foreground">
                    {f.tempMax}° <span className="font-normal text-muted-foreground">/ {f.tempMin}°</span>
                  </div>
                  <div className="flex items-center gap-2 text-[10px] text-muted-foreground">
                    <span className={f.precipPct >= 60 ? "text-blue-500 font-medium" : ""}>
                      💧 {f.precipPct}%
                    </span>
                    <span>{f.windMax} km/h</span>
                  </div>
                </div>
              ))}
        </div>
      )}
    </div>
  );
}
