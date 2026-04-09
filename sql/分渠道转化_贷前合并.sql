/*******************************************************************************
 * 查询名称: 分渠道转化+贷前指标 月度合并报表
 * 功能说明: 合并前链路转化漏斗指标（ads聚合表）与贷前交易额/终损指标（订单表）
 * 数据粒度: 月 + 渠道类别（5大渠道）
 * JOIN 逻辑: 两个CTE按 月份+渠道类别 FULL OUTER JOIN
 * 数据范围: 2025-01-01 起
 * 兼容性:   MaxCompute (ODPS) — 使用子查询预计算 channel_group 避免 GROUP BY 重复 CASE WHEN
 *
 * ⚠ 口径差异说明:
 *   - "实际首借金额" 来自 ads聚合表 (first_lend_user_lend_amt)，按 channel_subcategory 投放维度归因
 *   - "首借交易额"   来自 订单表 (loan_principal_amount WHERE first_reloan_flag_ot='首借')，按用户级营销归因
 *   两者在归因逻辑、首借定义、时间口径上均不同，不可直接对比
 *   如需统一口径，以订单表的"首借交易额"为准（最底层放款事实数据）
 ******************************************************************************/

-- ============================================================
-- CTE1: 前链路转化指标（来自3级渠道聚合表）
-- 数据源: ads_app_bi.ads_app_bi_channel_level_3_daily_aggregation_jsc_df
-- 归因口径: channel_subcategory（投放渠道维度）
-- ============================================================
WITH conversion AS (
    SELECT
        month_key,
        channel_group,

        -- 效率指标
        SUM(safe_t0_credit_num) * 1.0 / NULLIF(SUM(t0_apply_finish_num), 0)       AS safe_t0_pass_rate,           -- 1-3组T0过件率
        SUM(booked_fee) * 1.0 / NULLIF(SUM(all_t0_first_loan_amt_24h), 0)         AS all_t0_cps,                  -- 1-8组T0 CPS
        SUM(booked_fee)                                                             AS booked_fee,                  -- 花费(业务口径)
        SUM(all_t0_first_loan_amt_24h)                                              AS all_t0_first_loan_amt_24h,   -- 1-8T0首借24h金额
        SUM(t0_credit_num) * 1.0 / NULLIF(SUM(t0_apply_finish_num), 0)            AS all_t0_pass_rate,            -- 1-8组T0过件率
        SUM(booked_fee) * 1.0 / NULLIF(SUM(t0_apply_finish_num), 0)               AS t0_apply_cost,               -- T0申完成本
        SUM(t0_apply_finish_num)                                                    AS t0_apply_finish_num,         -- 非年龄拒绝T0申完量
        SUM(booked_fee) * 1.0 / SUM(SUM(booked_fee)) OVER(PARTITION BY month_key) AS fee_share,                   -- 花费结构
        SUM(m0_login_first_loan_amt_24h)                                            AS m0_login_first_loan_amt_24h, -- 1-8M0首登当月首借24h金额
        SUM(m0_login_first_loan_amt_24h) * 1.0 / NULLIF(SUM(all_t0_first_loan_amt_24h), 0) AS m0_t0_24h_ratio,    -- M0/T0比值

        -- 前链路
        SUM(expose_num)      AS expose_num,
        SUM(click_num)       AS click_num,
        SUM(media_side_cost) AS media_side_cost,
        SUM(first_login_num) AS first_login_num,

        -- T0转化
        SUM(t0_credit_num)        AS t0_credit_num,
        SUM(safe_t0_credit_num)   AS safe_t0_credit_num,
        SUM(t0_credit_limit)      AS t0_credit_limit,
        SUM(t0_first_lend_num)    AS t0_first_lend_num,

        -- T3转化
        SUM(t3_apply_finish_num)     AS t3_apply_finish_num,
        SUM(t3_credit_num)           AS t3_credit_num,
        SUM(safe_t3_credit_num)      AS safe_t3_credit_num,
        SUM(t3_credit_limit)         AS t3_credit_limit,
        SUM(t3_first_lend_num)       AS t3_first_lend_num,
        SUM(t3_first_lend_amt)       AS t3_first_lend_amt,

        -- 实际转化（⚠ 口径: ads聚合表投放维度，非订单级归因）
        SUM(actual_apply_finish_num)     AS actual_apply_finish_num,
        SUM(actual_apply_num)            AS actual_apply_num,
        SUM(actual_risk_pass_num)        AS actual_risk_pass_num,
        SUM(actual_credit_num)           AS actual_credit_num,
        SUM(actual_credit_limit)         AS actual_credit_limit,
        SUM(actual_credit_day_max_limit) AS actual_credit_day_max_limit,
        SUM(actual_first_lend_num)       AS actual_first_lend_num,
        SUM(actual_first_lend_amt)       AS actual_first_lend_amt,      -- ⚠ 与贷前"首借交易额"口径不同
        SUM(actual_safe_credit_num)      AS actual_safe_credit_num

    FROM (
        -- 内层子查询：预计算 month_key + channel_group，避免 MaxCompute GROUP BY 重复 CASE WHEN
        SELECT
            SUBSTR(calculate_date, 1, 7) AS month_key,
            CASE
                WHEN channel_subcategory = '精准营销' THEN '精准营销'
                WHEN channel_subcategory IN ('抖音', '抖音二组', '抖音中组', '抖音品专') THEN '抖音'
                WHEN channel_subcategory IN ('微信小程序', '腾讯二组', '腾讯中组', '腾讯h5') THEN '腾讯'
                WHEN channel_subcategory IN ('华为付费商店', 'OV+小米付费商店', '付费应用商店', 'VIVO信息流', '华为信息流', 'OPPO信息流', '荣耀付费商店', 'asa', '苹果付费商店') THEN '付费商店'
                WHEN channel_subcategory IN ('自然量', '公众号') THEN '免费渠道'
            END AS channel_group,
            `1_3_t0_credit_num`                      AS safe_t0_credit_num,
            booked_fee,
            `1_8_t0_first_lend_user_lend_amt_24h`    AS all_t0_first_loan_amt_24h,
            t0_credit_num,
            not_age_refuse_t0_apply_finish_num       AS t0_apply_finish_num,
            `1_8_m0_login_first_lend_user_lend_amt_24h` AS m0_login_first_loan_amt_24h,
            expose_num,
            click_num,
            media_side_cost,
            first_login_num,
            t0_credit_limit,
            t0_first_lend_num,
            t3_apply_finish_num,
            t3_credit_num,
            `1_3_t3_credit_num`                      AS safe_t3_credit_num,
            t3_credit_limit,
            t3_first_lend_num,
            t3_first_lend_user_lend_amt              AS t3_first_lend_amt,
            apply_finish_num                         AS actual_apply_finish_num,
            apply_num                                AS actual_apply_num,
            risk_pass_num                            AS actual_risk_pass_num,
            credit_num                               AS actual_credit_num,
            credit_limit                             AS actual_credit_limit,
            credit_day_max_credit_limit              AS actual_credit_day_max_limit,
            first_lend_num                           AS actual_first_lend_num,
            first_lend_user_lend_amt                 AS actual_first_lend_amt,
            `1_3_credit_num`                         AS actual_safe_credit_num
        FROM ads_app_bi.ads_app_bi_channel_level_3_daily_aggregation_jsc_df
        WHERE SUBSTR(calculate_date, 1, 10) >= '2025-01-01'
          AND channel_subcategory IN (
              '精准营销',
              '抖音', '抖音二组', '抖音中组', '抖音品专',
              '微信小程序', '腾讯二组', '腾讯中组', '腾讯h5',
              '华为付费商店', 'OV+小米付费商店', '付费应用商店', 'VIVO信息流', '华为信息流', 'OPPO信息流', '荣耀付费商店', 'asa', '苹果付费商店',
              '自然量', '公众号'
          )
    ) t
    GROUP BY month_key, channel_group
),

-- ============================================================
-- CTE2: 贷前指标 - 首借/复借交易额 & 终损（来自订单表）
-- 数据源: dwt_heavy_order_df × dwt_ot_take_rate_order_info_df × dwt_marketing_attribution_user_comprehensive_info_df
-- 归因口径: marketing_channel_group_name（用户级营销归因）
-- ⚠ 与CTE1归因口径不同：CTE1按投放渠道归因，CTE2按用户级营销归因
-- ============================================================
loan_loss AS (
    SELECT
        month_key,
        channel_group,

        -- 交易额（放款本金）——⚠ 口径: 订单级放款事实数据，用户级归因
        SUM(IF(first_reloan_flag_ot = '首借', loan_principal_amount, 0)) AS first_loan_amt,
        SUM(IF(first_reloan_flag_ot = '复借', loan_principal_amount, 0)) AS reloan_amt,
        SUM(loan_principal_amount)                                        AS total_loan_amt,

        -- 终损（预测本金损失）
        SUM(IF(first_reloan_flag_ot = '首借', risk_principal_loss_fst_24, 0)) AS first_loan_loss,
        SUM(IF(first_reloan_flag_ot = '复借', risk_principal_loss_fst_24, 0)) AS reloan_loss,
        SUM(risk_principal_loss_fst_24)                                        AS total_loss,

        -- 终损率
        SUM(IF(first_reloan_flag_ot = '首借', risk_principal_loss_fst_24, 0))
            / NULLIF(SUM(IF(first_reloan_flag_ot = '首借', loan_principal_amount, 0)), 0) AS first_loan_loss_rate,
        SUM(IF(first_reloan_flag_ot = '复借', risk_principal_loss_fst_24, 0))
            / NULLIF(SUM(IF(first_reloan_flag_ot = '复借', loan_principal_amount, 0)), 0) AS reloan_loss_rate,
        SUM(risk_principal_loss_fst_24)
            / NULLIF(SUM(loan_principal_amount), 0)                                        AS total_loss_rate

    FROM (
        -- 内层子查询：3表JOIN + 预计算 channel_group
        SELECT
            SUBSTR(t1.loan_date, 1, 7) AS month_key,
            CASE
                WHEN c.marketing_channel_group_name = '精准营销' THEN '精准营销'
                WHEN c.marketing_channel_group_name IN ('抖音', '抖音二组', '抖音中组', '抖音品专') THEN '抖音'
                WHEN c.marketing_channel_group_name IN ('微信小程序', '腾讯二组', '腾讯中组', '腾讯h5') THEN '腾讯'
                WHEN c.marketing_channel_group_name IN ('华为付费商店', 'OV+小米付费商店', '付费应用商店', 'VIVO信息流', '华为信息流', 'OPPO信息流', '荣耀付费商店', 'asa', '苹果付费商店') THEN '付费商店'
                WHEN c.marketing_channel_group_name IN ('自然量', '公众号') THEN '免费渠道'
            END AS channel_group,
            t1.loan_principal_amount,
            t1.first_reloan_flag_ot,
            t2.risk_principal_loss_fst_24
        FROM
            (SELECT uid, order_no, loan_date, loan_principal_amount, first_reloan_flag_ot
             FROM   dwt.dwt_heavy_order_df
             WHERE  ds = '20260406' AND loan_success_flag = 1 AND loan_date >= '2025-01-01') t1
        LEFT JOIN
            (SELECT order_no, risk_principal_loss_fst_24
             FROM   dwt.dwt_ot_take_rate_order_info_df
             WHERE  ds = date_format(last_day(add_months(to_date('20260406', 'yyyymmdd'), -1)), 'yyyyMMdd')) t2
        ON t1.order_no = t2.order_no
        LEFT JOIN
            (SELECT uid, marketing_channel_group_name
             FROM   dwt.dwt_marketing_attribution_user_comprehensive_info_df
             WHERE  ds = '20260406') c
        ON t1.uid = c.uid
        WHERE c.marketing_channel_group_name IN (
            '精准营销',
            '抖音', '抖音二组', '抖音中组', '抖音品专',
            '微信小程序', '腾讯二组', '腾讯中组', '腾讯h5',
            '华为付费商店', 'OV+小米付费商店', '付费应用商店', 'VIVO信息流', '华为信息流', 'OPPO信息流', '荣耀付费商店', 'asa', '苹果付费商店',
            '自然量', '公众号'
        )
    ) t
    GROUP BY month_key, channel_group
)

-- ============================================================
-- 最终合并: FULL JOIN 转化 + 贷前
-- ============================================================
SELECT
    -- 维度
    COALESCE(a.month_key, b.month_key)         AS 月份,
    COALESCE(a.channel_group, b.channel_group)  AS 渠道类别,

    -- ========== 转化效率指标 ==========
    a.safe_t0_pass_rate                         AS `1-3组T0过件率`,
    a.all_t0_cps                                AS `1-8组T0_CPS`,
    a.booked_fee                                AS 花费,
    a.all_t0_first_loan_amt_24h                 AS `1-8T0首借24h金额`,
    a.all_t0_pass_rate                          AS `1-8组T0过件率`,
    a.t0_apply_cost                             AS T0申完成本,
    a.t0_apply_finish_num                       AS 非年龄拒绝T0申完量,
    a.fee_share                                 AS 花费结构,
    a.m0_login_first_loan_amt_24h               AS `1-8M0首登当月首借24h金额`,
    a.m0_t0_24h_ratio                           AS 当月首登M0_T0_24h_交易比值,

    -- ========== 前链路 ==========
    a.expose_num                                AS 曝光量,
    a.click_num                                 AS 点击量,
    a.media_side_cost                           AS 媒体侧花费,
    a.first_login_num                           AS 首登数,

    -- ========== T0转化 ==========
    a.t0_credit_num                             AS T0授信数,
    a.safe_t0_credit_num                        AS T0安全授信数,
    a.t0_credit_limit                           AS T0授信额度,
    a.t0_first_lend_num                         AS T0首借人数,

    -- ========== T3转化 ==========
    a.t3_apply_finish_num                       AS T3申完数,
    a.t3_credit_num                             AS T3授信数,
    a.safe_t3_credit_num                        AS T3安全授信数,
    a.t3_credit_limit                           AS T3授信额度,
    a.t3_first_lend_num                         AS T3首借人数,
    a.t3_first_lend_amt                         AS T3首借金额,

    -- ========== 实际转化（ads聚合表口径）==========
    a.actual_apply_finish_num                   AS 实际申完人数,
    a.actual_apply_num                          AS 实际发起人数,
    a.actual_risk_pass_num                      AS 实际风险通过人数,
    a.actual_credit_num                         AS 实际授信人数,
    a.actual_credit_limit                       AS 实际授信额度,
    a.actual_credit_day_max_limit               AS 实际首次授信日最大授信额度,
    a.actual_first_lend_num                     AS 实际首借人数,
    a.actual_first_lend_amt                     AS 实际首借金额,           -- ⚠ ads聚合表口径，非订单级
    a.actual_safe_credit_num                    AS 实际1_3档授信人数,

    -- ========== 贷前指标: 交易额（订单表口径）==========
    b.first_loan_amt                            AS 首借交易额,             -- ⚠ 订单表口径，用户级归因
    b.reloan_amt                                AS 复借交易额,
    b.total_loan_amt                            AS 合计交易额,

    -- ========== 贷前指标: 终损 ==========
    b.first_loan_loss                           AS 首借终损,
    b.reloan_loss                               AS 复借终损,
    b.total_loss                                AS 合计终损,

    -- ========== 贷前指标: 终损率 ==========
    b.first_loan_loss_rate                      AS 首借终损率,
    b.reloan_loss_rate                          AS 复借终损率,
    b.total_loss_rate                           AS 合计终损率

FROM conversion a
FULL OUTER JOIN loan_loss b
    ON a.month_key = b.month_key
   AND a.channel_group = b.channel_group

ORDER BY 月份, 渠道类别
;
