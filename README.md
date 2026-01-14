# Dty
一个利用截图微信来监控收款记录的python程序

他可以配合另一个nodejs程序使用 或使用api来制作功能

通过截图识别文字然后提取关键词来确认金额和备注

拥有剔除 可以自动剔除自动续费和付款等不 影响正常使用

他依赖Tesseract-OCR 并需要将微信字体放大可以识别的状态

![主页面](/example/1.png)

框选微信文字部分 点击开始监控即可监控

然后访问127.0.0.1:5001/query_payment 可以看到所有订单

格式示例:

{"records":[{"actual_amount":"10.00","order_id":"debug_test_1768392333","payer_memo":"[\u8c03\u8bd5] 2026-01-14 20:05:33 | \u7528\u6237\u5907\u6ce8: 12345","payment_time":"2026-01-14 20:05:33","user_memo":"12345"}],"status":"success","total_count":1}

金额10 备注12345

