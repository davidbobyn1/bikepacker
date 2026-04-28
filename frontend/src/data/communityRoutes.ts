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
  prompt: string;
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
    prompt:
      "3 days in Kananaskis, Alberta. Mostly gravel, camping each night, aiming for 200–220 km total. Want big mountain climbs and minimal traffic. Strong intermediate rider.",
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
    prompt:
      "2-day loop from Fairfax, California. Mix of gravel and paved, camping at Pantoll or Olema. Want coastal views, around 150–170 km, intermediate fitness.",
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
    prompt:
      "3-day gravel loop in Vermont's Northeast Kingdom, starting from St. Johnsbury. Mostly dirt and gravel roads, camping or small inns, 220–250 km. Intermediate rider, want remote and forested.",
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
    prompt:
      "4 days through the Cairngorms, Scotland, starting from Aviemore. Mix of gravel tracks and rough doubletrack, wild camping each night, 260–290 km. Strong rider comfortable with remote and exposed terrain.",
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
    prompt:
      "2-day gravel loop from Girona, Spain. Famous cycling roads through the Garrotxa volcanic zone, mostly gravel, hotel or rural casa each night, 180–200 km. Intermediate to strong rider.",
  },
];
