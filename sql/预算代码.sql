/*******************************************************************************
 * 查询名称: 预算首借金额统计表
 * 功能说明: 按月份、渠道、客群统计首借金额
 * 数据粒度: 月 + 渠道类别 + 客群
 * 数据范围: 2025-01-01 起至当前分区日期
 * 更新频率: 每日
 * 业务用途: 预算管理平台核心数据源
 ******************************************************************************/

WITH user_base_info AS (
    -- 用户基础信息表：包含客群分类和渠道信息
    SELECT
        a.uid,
        a.marketing_channel_group_name,
        a.current_month,

        -- ==================== 客群分类逻辑 ====================
        -- 基于首次授信类型、渠道类型、授信时间等维度划分客群
        CASE
            -- 存量首登M0：初审用户，非API渠道，授信月=当前月，但首登日期在当前月之前
            WHEN a.first_credit_law_type = 'FIRST_AUDIT'
                 AND a.first_login_level1_channel_name <> 'API'
                 AND DATEDIFF(DATE(CONCAT(a.current_month, '-01')), DATE(a.first_credit_time_by_btch), 'MM') = 0
                 AND DATE(a.first_login_time_api_app_mp) < TRUNC(DATE(CONCAT(a.current_month, '-01')), 'MM')
                THEN '存量首登M0'

            -- 当月首登M0：初审用户，非API渠道，授信月=当前月，首登也在当前月
            WHEN a.first_credit_law_type = 'FIRST_AUDIT'
                 AND a.first_login_level1_channel_name <> 'API'
                 AND DATEDIFF(DATE(CONCAT(a.current_month, '-01')), DATE(a.first_credit_time_by_btch), 'MM') = 0
                THEN '当月首登M0'

            -- 初审M1+：初审用户，非API渠道，授信月距当前月>=1个月
            WHEN a.first_credit_law_type = 'FIRST_AUDIT'
                 AND a.first_login_level1_channel_name <> 'API'
                 AND DATEDIFF(DATE(CONCAT(a.current_month, '-01')), DATE(a.first_credit_time_by_btch), 'MM') >= 1
                THEN '初审M1+'

            -- 非初审-重申：非初审用户，重新申请类型
            WHEN a.first_credit_law_type <> 'FIRST_AUDIT'
                 AND a.first_credit_law_type = 'RE_APPLY'
                 AND DATEDIFF(DATE(CONCAT(a.current_month, '-01')), DATE(a.first_credit_time_by_btch), 'MM') >= 0
                THEN '非初审-重申'

            -- 非初审-重审及其他：贷前召回、重新审核等其他类型
            WHEN a.first_credit_law_type <> 'FIRST_AUDIT'
                 AND a.first_credit_law_type IN ('PRE_LOAN_RECALL', 'RE_AUDIT', 'OTHER')
                 AND DATEDIFF(DATE(CONCAT(a.current_month, '-01')), DATE(a.first_credit_time_by_btch), 'MM') >= 0
                THEN '非初审-重审及其他'

            -- API回流：初审用户，但来自API渠道
            WHEN a.first_credit_law_type = 'FIRST_AUDIT'
                 AND a.first_login_level1_channel_name = 'API'
                 AND DATEDIFF(DATE(CONCAT(a.current_month, '-01')), DATE(a.first_credit_time_by_btch), 'MM') >= 0
                THEN 'API回流'

            ELSE '其他'
        END AS user_group

    FROM
    -- MAPJOIN: tt 仅十几行月份，广播小表后允许非等值过滤
    (SELECT /*+ MAPJOIN(tt) */
         a.uid,
         a.marketing_channel_group_name,
         a.first_credit_law_type,
         a.first_login_level1_channel_name,
         a.first_credit_time_by_btch,
         a.first_login_time_api_app_mp,
         tt.current_month
     FROM dcube.dcube_v_user_info a
     JOIN (
         SELECT SUBSTR(date_key, 1, 7) AS current_month
         FROM cdmx.cdmx_dim_date_df
         WHERE ds = '${bizdate}'
           AND date_key >= '2025-01-01'
           AND SUBSTR(date_key, 1, 7) <= SUBSTR(TO_DATE('${bizdate}', 'yyyymmdd'), 1, 7)
         GROUP BY SUBSTR(date_key, 1, 7)
     ) tt
     ON 1 = 1
     WHERE a.ds = '${bizdate}'
       AND DATE(a.first_credit_time_by_btch) <= DATE(TO_DATE('${bizdate}', 'yyyymmdd'))
       AND SUBSTR(CAST(a.first_credit_time_by_btch AS STRING), 1, 7) <= tt.current_month
    ) a
),
first_loan_data AS (
    -- 首借数据表：每个用户的首笔动支金额（24小时内的动支汇总）
    SELECT
        a.uid,
        SUM(b.loan_principal_amount) AS loan_principal_amount,        -- 首借金额
        SUBSTR(b.loan_date, 1, 7) AS loan_month                       -- 首借月份
    FROM (
        -- 识别每个用户的首笔动支记录
        SELECT
            uid,
            apply_time
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
              AND business_type <> 'API_ASSET'                         -- 排除API资产
              AND loan_date <= DATE(TO_DATE('${bizdate}', 'yyyymmdd'))
              AND loan_success_flag = 1                                -- 只统计成功放款
        ) t
        WHERE rn = 1                                                   -- 只取首笔
    ) a
    LEFT JOIN (
        -- 首笔动支后24小时内的所有动支记录
        SELECT
            uid,
            apply_time,
            loan_date,
            loan_principal_amount
        FROM dwt.dwt_heavy_order_df
        WHERE ds = '${bizdate}'
          AND business_type <> 'API_ASSET'
          AND loan_date <= DATE(TO_DATE('${bizdate}', 'yyyymmdd'))
          AND loan_success_flag = 1
    ) b
        ON a.uid = b.uid
        AND DATEDIFF(b.apply_time, a.apply_time, 'HH') BETWEEN 0 AND 24   -- 24小时内动支
    GROUP BY a.uid, b.loan_date
),
channel_classified AS (
    -- 渠道分类表：统一渠道归类逻辑
    SELECT
        u.uid,
        u.current_month,
        u.user_group,

        -- ==================== 渠道类别分类（与三级渠道表保持一致）====================
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

    -- 关联首借数据：只保留在当月有首借的用户
    LEFT JOIN first_loan_data l
        ON u.uid = l.uid
        AND u.current_month = l.loan_month

    WHERE u.user_group IS NOT NULL                                     -- 过滤掉无效客群
    
)

-- 最终聚合：按月份、渠道、客群统计首借金额
SELECT
    -- ==================== 维度字段 ====================
    current_month AS 月份,                                              -- 月份(YYYY-MM格式)
    channel_category AS 渠道类别,                                       -- 渠道类别(5大类)
    user_group AS 客群,                                                 -- 客群分类(6大类)

    -- ==================== 指标字段 ====================
    SUM(loan_principal_amount) AS 首借金额                              -- 当月首借金额汇总

FROM channel_classified

WHERE channel_category not in ('其他')

GROUP BY
    current_month,
    channel_category,
    user_group

ORDER BY
    月份,
    渠道类别,
    客群
;

/*******************************************************************************
 * 业务逻辑说明:
 *
 * === 客群分类定义 ===
 * 1. 存量首登M0: 授信在当月，但首登日期早于当月（存量用户在当月授信）
 * 2. 当月首登M0: 授信在当月，首登也在当月（新用户当月授信）
 * 3. 初审M1+:    初审用户，授信月距当前月>=1个月（授信后1个月及以上才借款）
 * 4. 非初审-重申: 非初审用户，重新申请借款
 * 5. 非初审-重审及其他: 贷前召回、重新审核等其他非初审类型
 * 6. API回流:    来自API渠道的初审用户
 *
 * === 渠道分类定义 ===
 * 1. 精准营销: 精准营销渠道
 * 2. 抖音:     抖音系列渠道（含抖音、抖音二组、抖音中组、抖音品专）
 * 3. 腾讯:     腾讯系列渠道（含微信小程序、腾讯二组、腾讯中组、腾讯h5）
 * 4. 付费商店: 各大应用商店付费渠道（华为、OV、小米、VIVO、OPPO、苹果ASA等）
 * 5. 免费渠道: 自然量、公众号等免费获客渠道
 * 6. 其他:     未归类渠道
 *
 * === 首借金额计算逻辑 ===
 * - 识别每个用户的首笔放款记录
 * - 汇总首笔放款后24小时内的所有动支金额
 * - 按月份归集（以loan_date月份为准）
 * - 排除API资产(business_type <> 'API_ASSET')
 * - 只统计成功放款(loan_success_flag = 1)
 *
 * === 时间维度说明 ===
 * - current_month: 统计月份，从2025-01-01起至当前分区日期
 * - 每个用户在首次授信月份及之后的所有月份都会有记录
 * - 只有在当月有首借行为的记录才会有首借金额
 *
 * === 数据源说明 ===
 * - dcube.dcube_v_user_info: 用户基础信息表（客群分类依据）
 * - cdmx.cdmx_dim_date_df: 日期维度表（生成月份列表）
 * - dwt.dwt_heavy_order_df: 订单明细表（首借金额来源）
 * - 所有表均使用 ds = '${bizdate}' 分区
 *
 * === 与三级渠道表的关系 ===
 * - 维度对齐: 月份 + 渠道类别（一致）+ 客群（本表特有）
 * - 渠道分类: 使用相同的5大类分类逻辑
 * - 可联合使用: 本表提供预算视角，三级渠道表提供实际转化漏斗视角
 ******************************************************************************/
