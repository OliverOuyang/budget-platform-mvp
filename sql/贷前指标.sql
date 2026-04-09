-- ============================================================
-- 贷前指标：By月 By渠道 首借/复借 交易额 & 终损
-- 数据源：dwt_heavy_order_df × dwt_ot_take_rate_order_info_df × dwt_marketing_attribution_user_comprehensive_info_df
-- ============================================================

SELECT
    -- ==================== 维度 ====================
    substr(t1.loan_date, 1, 7)                          AS loan_month,          -- 放款月
    CASE
        WHEN c.marketing_channel_group_name = '精准营销'
            THEN '精准营销'
        WHEN c.marketing_channel_group_name IN ('抖音', '抖音二组', '抖音中组', '抖音品专')
            THEN '抖音'
        WHEN c.marketing_channel_group_name IN ('微信小程序', '腾讯二组', '腾讯中组', '腾讯h5')
            THEN '腾讯'
        WHEN c.marketing_channel_group_name IN ('百度信息流', '快手', '百度sem', '百度sem品专', '百度sem开屏', '广点通', 'B站', '粉丝通', '穿山甲')
            THEN '其他信息流'
        WHEN c.marketing_channel_group_name IN ('私域获客', '行业渠道')
            THEN '其他CPA渠道'
        WHEN c.marketing_channel_group_name = 'API'
            THEN 'API'
        WHEN c.marketing_channel_group_name IN ('华为付费商店', 'OV+小米付费商店', '付费应用商店', 'VIVO信息流', '华为信息流', 'OPPO信息流', '荣耀付费商店', 'asa', '苹果付费商店')
            THEN '付费商店'
        WHEN c.marketing_channel_group_name IN ('自然量', '公众号')
            THEN '免费渠道'
        WHEN c.marketing_channel_group_name = 'MGM'
            THEN 'MGM'
        ELSE '其他'
    END                                                 AS channel_group,       -- 渠道类别

    -- ==================== 交易额（放款本金） ====================
    sum(if(t1.first_reloan_flag_ot = '首借', t1.loan_principal_amount, 0))  AS first_loan_amt,      -- 首借交易额
    sum(if(t1.first_reloan_flag_ot = '复借', t1.loan_principal_amount, 0))  AS reloan_amt,           -- 复借交易额
    sum(t1.loan_principal_amount)                                            AS total_loan_amt,       -- 合计交易额

    -- ==================== 终损（预测本金损失） ====================
    sum(if(t1.first_reloan_flag_ot = '首借', t2.risk_principal_loss_fst_24, 0))  AS first_loan_loss,  -- 首借终损
    sum(if(t1.first_reloan_flag_ot = '复借', t2.risk_principal_loss_fst_24, 0))  AS reloan_loss,      -- 复借终损
    sum(t2.risk_principal_loss_fst_24)                                            AS total_loss,       -- 合计终损

    -- ==================== 终损率 = 终损 / 交易额 ====================
    sum(if(t1.first_reloan_flag_ot = '首借', t2.risk_principal_loss_fst_24, 0))
        / nullif(sum(if(t1.first_reloan_flag_ot = '首借', t1.loan_principal_amount, 0)), 0)  AS first_loan_loss_rate,  -- 首借终损率
    sum(if(t1.first_reloan_flag_ot = '复借', t2.risk_principal_loss_fst_24, 0))
        / nullif(sum(if(t1.first_reloan_flag_ot = '复借', t1.loan_principal_amount, 0)), 0)  AS reloan_loss_rate,      -- 复借终损率
    sum(t2.risk_principal_loss_fst_24)
        / nullif(sum(t1.loan_principal_amount), 0)                                            AS total_loss_rate        -- 合计终损率

FROM
    -- 订单主表：成功放款记录
    (
        SELECT uid, order_no, loan_date, loan_principal_amount, first_reloan_flag_ot
        FROM   dwt.dwt_heavy_order_df
        WHERE  ds = '${bizdate}'
          AND  loan_success_flag = 1
    ) t1

    -- 订单维度表：首复借标签 + 终损预测值
    LEFT JOIN (
        SELECT order_no, risk_principal_loss_fst_24
        FROM   dwt.dwt_ot_take_rate_order_info_df
        WHERE  ds = date_format(last_day(add_months(to_date('${bizdate}', 'yyyymmdd'), -1)), 'yyyyMMdd')
    ) t2
    ON t1.order_no = t2.order_no

    -- 用户归因表：渠道分组
    LEFT JOIN (
        SELECT uid, marketing_channel_group_name
        FROM   dwt.dwt_marketing_attribution_user_comprehensive_info_df
        WHERE  ds = '${bizdate}'
    ) c
    ON t1.uid = c.uid

GROUP BY
    substr(t1.loan_date, 1, 7),
    CASE
        WHEN c.marketing_channel_group_name = '精准营销'
            THEN '精准营销'
        WHEN c.marketing_channel_group_name IN ('抖音', '抖音二组', '抖音中组', '抖音品专')
            THEN '抖音'
        WHEN c.marketing_channel_group_name IN ('微信小程序', '腾讯二组', '腾讯中组', '腾讯h5')
            THEN '腾讯'
        WHEN c.marketing_channel_group_name IN ('百度信息流', '快手', '百度sem', '百度sem品专', '百度sem开屏', '广点通', 'B站', '粉丝通', '穿山甲')
            THEN '其他信息流'
        WHEN c.marketing_channel_group_name IN ('私域获客', '行业渠道')
            THEN '其他CPA渠道'
        WHEN c.marketing_channel_group_name = 'API'
            THEN 'API'
        WHEN c.marketing_channel_group_name IN ('华为付费商店', 'OV+小米付费商店', '付费应用商店', 'VIVO信息流', '华为信息流', 'OPPO信息流', '荣耀付费商店', 'asa', '苹果付费商店')
            THEN '付费商店'
        WHEN c.marketing_channel_group_name IN ('自然量', '公众号')
            THEN '免费渠道'
        WHEN c.marketing_channel_group_name = 'MGM'
            THEN 'MGM'
        ELSE '其他'
    END

ORDER BY
    loan_month,
    channel_group
;
