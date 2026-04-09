/*******************************************************************************
 * 查询名称: 预算首借金额统计表（周粒度）
 * 功能说明: 按周、渠道、客群统计首借金额，用于MMM模型训练
 * 数据粒度: 周（周一起始）+ 渠道类别（5大渠道）+ 客群
 * 数据范围: 2025-01-01 起
 * 兼容性:   MaxCompute (ODPS) — 使用 MAPJOIN + 子查询模式
 *
 * 与月粒度版本(预算代码.sql)的差异:
 *   - 时间维度从月改为周（周一起始日期，如 2025-01-06）
 *   - 客群分类逻辑不变（M0/M1+仍为月级概念，基于该周所属月份判定）
 *   - 首借金额按放款所在周归集
 *
 * 周起始日计算方法:
 *   以 2025-01-06（已知周一）为锚点，通过 DATEDIFF + PMOD 计算任意日期的偏移量
 *   offset = PMOD(DATEDIFF(date, '2025-01-06', 'dd'), 7)  -- 0=周一, 1=周二, ..., 6=周日
 *   week_start = DATEADD(date, -offset, 'dd')
 ******************************************************************************/

WITH
-- ============================================================
-- 周维度表：生成每周起始日期（周一）
-- ============================================================
week_dim AS (
    SELECT DISTINCT week_start
    FROM (
        SELECT
            TO_CHAR(
                DATEADD(
                    TO_DATE(date_key, 'yyyy-mm-dd'),
                    -CAST(PMOD(DATEDIFF(TO_DATE(date_key, 'yyyy-mm-dd'), TO_DATE('2025-01-06', 'yyyy-mm-dd'), 'dd'), 7) AS BIGINT),
                    'dd'
                ),
                'yyyy-mm-dd'
            ) AS week_start
        FROM cdmx.cdmx_dim_date_df
        WHERE ds = '${bizdate}'
          AND date_key >= '2025-01-01'
          AND date_key <= TO_CHAR(TO_DATE('${bizdate}', 'yyyymmdd'), 'yyyy-mm-dd')
    ) d
),

-- ============================================================
-- 用户基础信息 × 周维度（MAPJOIN 广播小表）
-- 客群分类基于该周所属月份（M0/M1+为月级概念）
-- ============================================================
user_base_info AS (
    SELECT
        a.uid,
        a.marketing_channel_group_name,
        a.week_start,

        -- ==================== 客群分类逻辑（与月版本一致）====================
        CASE
            -- 存量首登M0：初审用户，非API渠道，授信月=该周所属月，首登日期早于该月
            WHEN a.first_credit_law_type = 'FIRST_AUDIT'
                 AND a.first_login_level1_channel_name <> 'API'
                 AND DATEDIFF(DATE(CONCAT(SUBSTR(a.week_start, 1, 7), '-01')), DATE(a.first_credit_time_by_btch), 'MM') = 0
                 AND DATE(a.first_login_time_api_app_mp) < TRUNC(DATE(CONCAT(SUBSTR(a.week_start, 1, 7), '-01')), 'MM')
                THEN '存量首登M0'

            -- 当月首登M0：初审用户，非API渠道，授信月=该周所属月，首登也在该月
            WHEN a.first_credit_law_type = 'FIRST_AUDIT'
                 AND a.first_login_level1_channel_name <> 'API'
                 AND DATEDIFF(DATE(CONCAT(SUBSTR(a.week_start, 1, 7), '-01')), DATE(a.first_credit_time_by_btch), 'MM') = 0
                THEN '当月首登M0'

            -- 初审M1+：初审用户，非API渠道，授信月距该周所属月>=1个月
            WHEN a.first_credit_law_type = 'FIRST_AUDIT'
                 AND a.first_login_level1_channel_name <> 'API'
                 AND DATEDIFF(DATE(CONCAT(SUBSTR(a.week_start, 1, 7), '-01')), DATE(a.first_credit_time_by_btch), 'MM') >= 1
                THEN '初审M1+'

            -- 非初审-重申
            WHEN a.first_credit_law_type <> 'FIRST_AUDIT'
                 AND a.first_credit_law_type = 'RE_APPLY'
                 AND DATEDIFF(DATE(CONCAT(SUBSTR(a.week_start, 1, 7), '-01')), DATE(a.first_credit_time_by_btch), 'MM') >= 0
                THEN '非初审-重申'

            -- 非初审-重审及其他
            WHEN a.first_credit_law_type <> 'FIRST_AUDIT'
                 AND a.first_credit_law_type IN ('PRE_LOAN_RECALL', 'RE_AUDIT', 'OTHER')
                 AND DATEDIFF(DATE(CONCAT(SUBSTR(a.week_start, 1, 7), '-01')), DATE(a.first_credit_time_by_btch), 'MM') >= 0
                THEN '非初审-重审及其他'

            -- API回流
            WHEN a.first_credit_law_type = 'FIRST_AUDIT'
                 AND a.first_login_level1_channel_name = 'API'
                 AND DATEDIFF(DATE(CONCAT(SUBSTR(a.week_start, 1, 7), '-01')), DATE(a.first_credit_time_by_btch), 'MM') >= 0
                THEN 'API回流'

            ELSE '其他'
        END AS user_group

    FROM (
        -- MAPJOIN: week_dim 仅60-70行，广播后允许非等值过滤
        SELECT /*+ MAPJOIN(tt) */
            a.uid,
            a.marketing_channel_group_name,
            a.first_credit_law_type,
            a.first_login_level1_channel_name,
            a.first_credit_time_by_btch,
            a.first_login_time_api_app_mp,
            tt.week_start
        FROM dcube.dcube_v_user_info a
        JOIN week_dim tt
        ON 1 = 1
        WHERE a.ds = '${bizdate}'
          AND DATE(a.first_credit_time_by_btch) <= DATE(TO_DATE('${bizdate}', 'yyyymmdd'))
          -- 只展开授信月 <= 该周所属月的记录
          AND SUBSTR(CAST(a.first_credit_time_by_btch AS STRING), 1, 7) <= SUBSTR(tt.week_start, 1, 7)
    ) a
),

-- ============================================================
-- 首借数据（按周归集）
-- 逻辑同月版本：取每个用户首笔动支后24小时内的所有动支金额
-- 时间维度改为 loan_week（放款日所在周的周一）
-- ============================================================
first_loan_data AS (
    SELECT
        uid,
        SUM(loan_principal_amount) AS loan_principal_amount,
        loan_week
    FROM (
        -- 内层：预计算 loan_week 避免 MaxCompute GROUP BY 表达式不匹配
        SELECT
            a.uid,
            b.loan_principal_amount,
            TO_CHAR(
                DATEADD(
                    TO_DATE(b.loan_date, 'yyyy-mm-dd'),
                    -CAST(PMOD(DATEDIFF(TO_DATE(b.loan_date, 'yyyy-mm-dd'), TO_DATE('2025-01-06', 'yyyy-mm-dd'), 'dd'), 7) AS BIGINT),
                    'dd'
                ),
                'yyyy-mm-dd'
            ) AS loan_week
        FROM (
            -- 识别每个用户的首笔动支记录
            SELECT uid, apply_time
            FROM (
                SELECT
                    uid,
                    apply_time,
                    ROW_NUMBER() OVER (
                        PARTITION BY uid
                        ORDER BY loan_date, apply_time, loan_record_crt_time, SUBSTR(order_no, 3)
                    ) AS rn
                FROM dwt.dwt_heavy_order_df
                WHERE ds = '${bizdate}'
                  AND business_type <> 'API_ASSET'
                  AND loan_date <= DATE(TO_DATE('${bizdate}', 'yyyymmdd'))
                  AND loan_success_flag = 1
            ) t
            WHERE rn = 1
        ) a
        LEFT JOIN (
            -- 首笔动支后24小时内的所有动支记录
            SELECT uid, apply_time, loan_date, loan_principal_amount
            FROM dwt.dwt_heavy_order_df
            WHERE ds = '${bizdate}'
              AND business_type <> 'API_ASSET'
              AND loan_date <= DATE(TO_DATE('${bizdate}', 'yyyymmdd'))
              AND loan_success_flag = 1
        ) b
            ON a.uid = b.uid
            AND DATEDIFF(b.apply_time, a.apply_time, 'HH') BETWEEN 0 AND 24
    ) t
    GROUP BY uid, loan_week
),

-- ============================================================
-- 渠道分类（与月版本一致）
-- ============================================================
channel_classified AS (
    SELECT
        u.uid,
        u.week_start,
        u.user_group,

        CASE
            WHEN u.marketing_channel_group_name = '精准营销' THEN '精准营销'
            WHEN u.marketing_channel_group_name IN ('抖音', '抖音二组', '抖音中组', '抖音品专') THEN '抖音'
            WHEN u.marketing_channel_group_name IN ('微信小程序', '腾讯二组', '腾讯中组', '腾讯h5') THEN '腾讯'
            WHEN u.marketing_channel_group_name IN (
                '华为付费商店', 'OV+小米付费商店', '付费应用商店', 'VIVO信息流',
                '华为信息流', 'OPPO信息流', '荣耀付费商店', 'asa', '苹果付费商店'
            ) THEN '付费商店'
            WHEN u.marketing_channel_group_name IN ('自然量', '公众号') THEN '免费渠道'
            ELSE '其他'
        END AS channel_category,

        l.loan_principal_amount

    FROM user_base_info u

    -- 关联首借数据：按周匹配
    LEFT JOIN first_loan_data l
        ON u.uid = l.uid
        AND u.week_start = l.loan_week

    WHERE u.user_group IS NOT NULL
)

-- ============================================================
-- 最终聚合：按周 + 渠道 + 客群
-- ============================================================
SELECT
    week_start       AS 周起始日,
    channel_category AS 渠道类别,
    user_group       AS 客群,
    SUM(loan_principal_amount) AS 首借金额

FROM channel_classified

WHERE channel_category NOT IN ('其他')

GROUP BY
    week_start,
    channel_category,
    user_group

ORDER BY
    周起始日,
    渠道类别,
    客群
;

/*******************************************************************************
 * 业务逻辑说明:
 *
 * === 与月版本的核心差异 ===
 * 1. 时间维度: 月 → 周（周一起始日期）
 * 2. 用户展开: 每个用户从授信月起，在所有后续周中都有记录
 * 3. 客群判定: 仍基于月级概念 — 用 SUBSTR(week_start, 1, 7) 取该周所属月份判定M0/M1+
 * 4. 首借归集: 按放款日所在周（而非月）聚合
 *
 * === 跨月周处理 ===
 * - 月末跨周（如2025-01-27~2025-02-02）按周一日期(01-27)归属1月
 * - 同一周内的用户客群以该周一所属月份判定
 * - 这意味着跨月周的用户客群统一按周一的月份确定，不会出现同一周内客群跳变
 *
 * === MMM模型适配 ===
 * - 输出粒度: ~68周 × 5渠道 × 6客群 ≈ 2000行（适合模型训练）
 * - 可与周粒度的渠道花费数据按 周起始日+渠道 JOIN 作为模型输入
 * - 建议将 API回流 和 其他 客群排除后使用
 ******************************************************************************/
