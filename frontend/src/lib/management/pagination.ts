export type PageInfo = {
  totalPages: number;
  rangeStart: number;
  rangeEnd: number;
};

export function getPageInfo(
  page: number,
  total: number,
  pageSize: number,
): PageInfo {
  const totalPages = Math.max(1, Math.ceil(total / pageSize));
  const rangeStart = total === 0 ? 0 : (page - 1) * pageSize + 1;
  const rangeEnd = Math.min(page * pageSize, total);

  return { totalPages, rangeStart, rangeEnd };
}
