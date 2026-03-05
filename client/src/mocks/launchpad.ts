export type LaunchpadProjectCard = {
  id: string;
  title: string;
  lastActiveText: string;
  thumbnailClassName: string;
  aiStatus: string;
  lastAiEdit: string;
  storageType: "cloud" | "local";
  clipCount: number;
};

// TODO(contract): 使用真实 `GET /api/v1/projects` 响应替换本地 mock。
export const MOCK_LAUNCHPAD_PROJECTS: LaunchpadProjectCard[] = [
  {
    id: "lp_proj_1",
    title: "Beach Trip Vlog",
    lastActiveText: "2 小时前",
    thumbnailClassName: "launch-thumb-cyan",
    aiStatus: "Analyzed 42 clips",
    lastAiEdit: "Replaced intro sequence",
    storageType: "cloud",
    clipCount: 42,
  },
  {
    id: "lp_proj_2",
    title: "Product Launch Promo_v2",
    lastActiveText: "昨天 14:30",
    thumbnailClassName: "launch-thumb-indigo",
    aiStatus: "Ready for export",
    lastAiEdit: "Applied color grading patch",
    storageType: "cloud",
    clipCount: 23,
  },
  {
    id: "lp_proj_3",
    title: "Tech Review - Sony A7CII",
    lastActiveText: "3 天前",
    thumbnailClassName: "launch-thumb-zinc",
    aiStatus: "Pending media link",
    lastAiEdit: "Generated rough cut",
    storageType: "local",
    clipCount: 8,
  },
  {
    id: "lp_proj_4",
    title: "Japan Travel Cinematic",
    lastActiveText: "5 天前",
    thumbnailClassName: "launch-thumb-rose",
    aiStatus: "Analyzed 105 clips",
    lastAiEdit: "Matched music beats",
    storageType: "cloud",
    clipCount: 105,
  },
];

// TODO(contract): 使用真实 `POST /api/v1/projects` 创建项目。
export const MOCK_LAUNCHPAD_HINTS = [
  "A fast-paced recap of my Tokyo trip",
  "一个 30 秒的产品开场，节奏紧凑",
  "生成旅行 vlog 的第一版粗剪",
];
