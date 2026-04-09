/*******************************************************************************
 * 查询名称: 分渠道转化指标月度汇总(3级渠道)
 * 功能说明: 按月统计各渠道的转化漏斗指标和效率指标
 * 数据粒度: 月 + 渠道类别
 * 数据范围: 2026-03-13 起
 * 更新频率: 每日
 ******************************************************************************/

SELECT
    -- ==================== 维度字段 ====================
    SUBSTR(calculate_date, 1, 7) AS 月份,  -- 月份(YYYY-MM格式)

    -- 渠道类别分类(合并细分渠道为大类,排除"其他")
    CASE
        WHEN channel_subcategory = '精准营销' THEN '精准营销'
        WHEN channel_subcategory IN ('抖音', '抖音二组', '抖音中组', '抖音品专') THEN '抖音'
        WHEN channel_subcategory IN ('微信小程序', '腾讯二组', '腾讯中组', '腾讯h5') THEN '腾讯'
        WHEN channel_subcategory IN ('华为付费商店', 'OV+小米付费商店', '付费应用商店', 'VIVO信息流', '华为信息流', 'OPPO信息流', '荣耀付费商店', 'asa', '苹果付费商店') THEN '付费商店'
        WHEN channel_subcategory IN ('自然量', '公众号') THEN '免费渠道'
        ELSE NULL  -- 其他渠道类别将被WHERE条件过滤
    END AS 渠道类别,

    -- ==================== 关键效率指标 ====================
    -- 1-3组(安全资产)T0过件率
    SUM(`1_3_t0_credit_num`) * 1.0 / NULLIF(SUM(not_age_refuse_t0_apply_finish_num), 0) AS `1-3T0过件率`,

    -- 1-8组(全量)T0 CPS(每授信成本)
    SUM(booked_fee) * 1.0 / NULLIF(SUM(1_8_t0_first_lend_user_lend_amt_24h), 0) AS `1-8T0CPS`,

    -- 花费(业务口径)
    SUM(booked_fee) AS 花费,

    -- 1-8组(全量)T0交易额
    SUM(1_8_t0_first_lend_user_lend_amt_24h) AS `1-8T0首借24h借款金额`,

    -- 1-8组(全量)T0过件率
    SUM(t0_credit_num) * 1.0 / NULLIF(SUM(not_age_refuse_t0_apply_finish_num), 0) AS `1-8T0过件率`,

    -- T0申完成本
    SUM(booked_fee) * 1.0 / NULLIF(SUM(not_age_refuse_t0_apply_finish_num), 0)AS T0申完成本,

    -- T0申完量
    SUM(not_age_refuse_t0_apply_finish_num) AS 非年龄拒绝T0申完量,

    -- 花费结构(该渠道在当月总花费中的占比)
    SUM(booked_fee) * 1.0 / SUM(SUM(booked_fee)) OVER(PARTITION BY SUBSTR(calculate_date, 1, 7)) AS 花费结构,

    -- 1-8M0首登当月首借24h借款金额
    SUM(1_8_m0_login_first_lend_user_lend_amt_24h) AS 1_8M0首登当月首借24h借款金额,

    -- 当月首登M0_T0_24h_交易比值
    SUM(1_8_m0_login_first_lend_user_lend_amt_24h) * 1.0 / NULLIF(SUM(1_8_t0_first_lend_user_lend_amt_24h), 0) AS 当月首登M0_T0_24h_交易比值,

    -- ==================== 前链路指标(曝光维度) ====================
    SUM(expose_num) AS 曝光量,
    SUM(click_num) AS 点击量,
    SUM(media_side_cost) AS 媒体侧花费,

    -- ==================== 中链路指标(首登维度) ====================
    SUM(first_login_num) AS 首登数,

    -- ==================== T0转化指标(首次登录当天) ====================
    SUM(t0_credit_num) AS T0授信数,
    SUM(`1_3_t0_credit_num`) AS T0安全授信数,  -- 对应A卡1-3档位
    SUM(t0_credit_limit) AS T0授信额度,
    SUM(t0_first_lend_num) AS T0首借人数,

    -- ==================== T3转化指标(首次登录后3天) ====================
    SUM(t3_apply_finish_num) AS T3申完数,
    SUM(t3_credit_num) AS T3授信数,
    SUM(`1_3_t3_credit_num`) AS T3安全授信数,
    SUM(t3_credit_limit) AS T3授信额度,
    SUM(t3_first_lend_num) AS T3首借人数,
    SUM(t3_first_lend_user_lend_amt) AS T3首借金额,

    -- ==================== 全量实际转化指标 ====================
    SUM(apply_finish_num) AS 实际申完人数,
    SUM(apply_num) AS 实际发起人数,
    SUM(risk_pass_num) AS 实际风险通过人数,
    SUM(credit_num) AS 实际授信人数,
    SUM(credit_limit) AS 实际授信额度,
    SUM(credit_day_max_credit_limit) AS 实际首次授信日最大授信额度,
    SUM(first_lend_num) AS 实际首借人数,
    SUM(first_lend_user_lend_amt) AS 实际首借金额,
    SUM(`1_3_credit_num`) AS 实际1_3档授信人数

FROM ads_app_bi.ads_app_bi_channel_level_3_daily_aggregation_jsc_df

WHERE
    SUBSTR(calculate_date, 1, 10) >= '2025-01-01'
    -- 只保留指定的渠道类别
    AND channel_subcategory IN (
        '精准营销',
        '抖音', '抖音二组', '抖音中组', '抖音品专',
        '微信小程序', '腾讯二组', '腾讯中组', '腾讯h5',
        '华为付费商店', 'OV+小米付费商店', '付费应用商店', 'VIVO信息流', '华为信息流', 'OPPO信息流', '荣耀付费商店', 'asa', '苹果付费商店',
        '自然量', '公众号'
    )

GROUP BY
    SUBSTR(calculate_date, 1, 7),  -- 按月分组
    CASE
        WHEN channel_subcategory = '精准营销' THEN '精准营销'
        WHEN channel_subcategory IN ('抖音', '抖音二组', '抖音中组', '抖音品专') THEN '抖音'
        WHEN channel_subcategory IN ('微信小程序', '腾讯二组', '腾讯中组', '腾讯h5') THEN '腾讯'
        WHEN channel_subcategory IN ('华为付费商店', 'OV+小米付费商店', '付费应用商店', 'VIVO信息流', '华为信息流', 'OPPO信息流', '荣耀付费商店', 'asa', '苹果付费商店') THEN '付费商店'
        WHEN channel_subcategory IN ('自然量', '公众号') THEN '免费渠道'
        ELSE NULL
    END

ORDER BY
    月份,
    渠道类别
;

/*******************************************************************************
 * 字段说明:
 *
 * 效率指标:
 * - 1-3组T0过件率: T0安全授信数(A卡1-3档) / T0申完数
 * - 1-8组T0CPS: 花费 / T0授信数(全档位)
 * - 1-8组T0过件率: T0授信数 / T0申完数
 * - T0申完成本: 花费 / T0申完数
 * - 花费结构: 该渠道在当月总花费中的占比(按月分区计算)
 *
 * 转化漏斗:
 * 曝光 -> 点击 -> 首登 -> T0申完 -> T0授信 -> T0首借
 *
 * 时间维度:
 * - T0: 首次登录当天
 * - T3: 首次登录后3天内
 * - 实际: 全生命周期累计
 *
 * 资产分组:
 * - 1-3组: 安全资产(A卡1-3档位)
 * - 1-8组: 全量资产(所有档位)
 ******************************************************************************/
