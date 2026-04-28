export interface CommunityRoute {
  id: string;
  emoji: string;
  title: string;
  region: string;
  distanceKm: number;
  days: number;
  tags: string[];
  description: string;
  riderNote: string;
  url: string;
  urlLabel: string;
}

export const COMMUNITY_ROUTES: CommunityRoute[] = [
  {
    id: "kananaskis-loop",
    emoji: "🏔️",
    title: "Kananaskis High Rockies Loop",
    region: "Alberta, Canada",
    distanceKm: 210,
    days: 3,
    tags: ["Gravel", "Camping", "Big climbs"],
    description: "High alpine passes, zero traffic, one gas-station resupply at Barrier Lake.",
    riderNote: "Rode September · Hit peak fall colour",
    url: "https://bikepacking.com/routes/kananaskis-high-rockies-trail/",
    urlLabel: "bikepacking.com",
  },
  {
    id: "marin-point-reyes",
    emoji: "🌊",
    title: "Marin Headlands & Point Reyes",
    region: "North Bay, California",
    distanceKm: 160,
    days: 2,
    tags: ["Coastal", "Gravel", "Mixed surface"],
    description: "Fog, redwoods, and the Pacific coast in a single overnight from the Golden Gate.",
    riderNote: "Rode March · Cold but dry, wildflowers out",
    url: "https://www.ridewithgps.com/find/search?keywords=marin+headlands+point+reyes+bikepacking",
    urlLabel: "ridewithgps.com",
  },
  {
    id: "vermont-kingdom",
    emoji: "🍂",
    title: "Vermont Kingdom Gravel",
    region: "Northeast Kingdom, Vermont",
    distanceKm: 240,
    days: 3,
    tags: ["Gravel", "Remote", "Fall foliage"],
    description: "Dirt roads through covered-bridge country — the original American gravel.",
    riderNote: "Rode October · Mud-free, colours peaking",
    url: "https://bikepacking.com/routes/northeast-kingdom-loop/",
    urlLabel: "bikepacking.com",
  },
  {
    id: "cairngorms-traverse",
    emoji: "🏴󠁧󠁢󠁳󠁣󠁴󠁿",
    title: "Scottish Highlands Traverse",
    region: "Cairngorms, Scotland",
    distanceKm: 280,
    days: 4,
    tags: ["Remote", "Wild camping", "Hike-a-bike"],
    description: "Lochs, heather moorland, and bothies — bring a bothy bag and waterproofs.",
    riderNote: "Rode June · 18 hours of daylight, midges manageable",
    url: "https://bikepacking.com/routes/cairngorms-loop/",
    urlLabel: "bikepacking.com",
  },
  {
    id: "girona-gravel",
    emoji: "🫒",
    title: "Girona Gravel Classic",
    region: "Catalonia, Spain",
    distanceKm: 190,
    days: 2,
    tags: ["Gravel", "Cycling culture", "Espresso stops"],
    description: "The roads pro teams train on — volcanic gravel, olive groves, and great coffee.",
    riderNote: "Rode April · Perfect temps, quiet roads",
    url: "https://www.ridewithgps.com/find/search?keywords=girona+gravel+garrotxa",
    urlLabel: "ridewithgps.com",
  },
];
