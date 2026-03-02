SELECT
    db.name AS DatabaseName,
    CAST(SUM(mf.size) * 8 / 1024 AS DECIMAL(10,2)) AS TotalSizeMB
FROM sys.databases db
JOIN sys.master_files mf ON db.database_id = mf.database_id
GROUP BY db.name
ORDER BY TotalSizeMB DESC;



SELECT
    n.OwnerName,
    CAST(SUM(mf.size) / 131072.0 AS DECIMAL(12,2)) AS TotalSizeGB 
FROM sys.databases AS db
JOIN sys.master_files AS mf
  ON db.database_id = mf.database_id
CROSS APPLY (
    SELECT
        hy1 = CHARINDEX('-', db.name),
        hy2 = CHARINDEX('-', db.name, CHARINDEX('-', db.name) + 1),
        hy3 = CHARINDEX('-', db.name, CHARINDEX('-', db.name, CHARINDEX('-', db.name) + 1) + 1),
        hy4 = CHARINDEX('-', db.name, CHARINDEX('-', db.name, CHARINDEX('-', db.name, CHARINDEX('-', db.name) + 1) + 1) + 1)
) AS h
CROSS APPLY (
    SELECT OwnerName =
        CASE WHEN h.hy3 > 0
        THEN SUBSTRING(
            db.name,
            h.hy3 + 1,
            ISNULL(NULLIF(h.hy4, 0), LEN(db.name) + 1) - (h.hy3 + 1)
        )
        END
) AS n
WHERE n.OwnerName IS NOT NULL
GROUP BY n.OwnerName
ORDER BY TotalSizeGB DESC;