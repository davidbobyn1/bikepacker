import { motion } from "framer-motion";
import { ExternalLink, CheckCircle2 } from "lucide-react";
import { COMMUNITY_ROUTES } from "../../data/communityRoutes";

export default function CommunityRoutes() {
  return (
    <div className="space-y-4">
      {/* Section header */}
      <div className="flex items-center gap-3">
        <h2 className="font-serif text-lg text-foreground">Routes riders loved</h2>
        <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full bg-primary/10 text-primary text-[10px] font-semibold uppercase tracking-wider">
          <CheckCircle2 className="w-3 h-3" /> Community picks
        </span>
      </div>

      {/* Horizontal scroll on mobile, wrapped grid on larger screens */}
      <div className="flex gap-3 overflow-x-auto pb-2 sm:grid sm:grid-cols-2 sm:overflow-visible sm:pb-0 lg:grid-cols-3 -mx-4 px-4 sm:mx-0 sm:px-0">
        {COMMUNITY_ROUTES.map((route, i) => (
          <motion.div
            key={route.id}
            initial={{ opacity: 0, y: 16 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: i * 0.07, duration: 0.35 }}
            className="flex-shrink-0 w-[260px] sm:w-auto bg-card border border-border rounded-xl p-4 flex flex-col hover:border-primary/40 hover:shadow-md transition-all"
          >
            {/* Emoji + region */}
            <div className="flex items-center gap-2 mb-2">
              <span className="text-xl leading-none">{route.emoji}</span>
              <span className="text-[11px] font-medium text-muted-foreground truncate">
                {route.region}
              </span>
            </div>

            {/* Title */}
            <h3 className="font-serif text-[15px] text-foreground leading-snug mb-1">
              {route.title}
            </h3>

            {/* Description */}
            <p className="text-xs text-muted-foreground leading-relaxed mb-3 flex-1">
              {route.description}
            </p>

            {/* Tags */}
            <div className="flex flex-wrap gap-1 mb-3">
              {route.tags.map((tag) => (
                <span
                  key={tag}
                  className="px-1.5 py-0.5 rounded bg-secondary text-secondary-foreground text-[10px] font-medium"
                >
                  {tag}
                </span>
              ))}
            </div>

            {/* Stats */}
            <div className="text-xs font-medium text-foreground mb-1">
              {route.distanceKm} km · {route.days} {route.days === 1 ? "day" : "days"}
            </div>

            {/* Rider note */}
            <p className="text-[11px] italic text-muted-foreground mb-3">
              {route.riderNote}
            </p>

            {/* CTA — external link */}
            <a
              href={route.url}
              target="_blank"
              rel="noopener noreferrer"
              className="w-full inline-flex items-center justify-center gap-1.5 px-3 py-2 rounded-lg bg-primary/10 text-primary text-xs font-medium hover:bg-primary/20 active:bg-primary/30 transition-colors"
            >
              View on {route.urlLabel} <ExternalLink className="w-3 h-3" />
            </a>
          </motion.div>
        ))}
      </div>
    </div>
  );
}
