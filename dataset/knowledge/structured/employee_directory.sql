-- 员工主数据（快照 2026-08-31）
CREATE TABLE employee_directory (
  employee_id TEXT PRIMARY KEY,
  name TEXT,
  department TEXT,
  region TEXT,
  role TEXT,
  grade TEXT,
  employment_type TEXT,
  status TEXT
);
INSERT INTO employee_directory VALUES ('E001','陈明远','财务部','中国大陆','管理人员','M5','正式','在职');
INSERT INTO employee_directory VALUES ('E002','赵国强','采购部','中国大陆','管理人员','M4','正式','在职');
INSERT INTO employee_directory VALUES ('E003','孙丽华','人力资源部','中国大陆','管理人员','M4','正式','在职');
INSERT INTO employee_directory VALUES ('E004','周正','法务部','中国大陆','管理人员','M4','正式','在职');
INSERT INTO employee_directory VALUES ('E005','马俊','销售部','中国大陆','管理人员','M5','正式','在职');
INSERT INTO employee_directory VALUES ('E006','吴敏','运营部','中国大陆','管理人员','M4','正式','在职');
INSERT INTO employee_directory VALUES ('E007','郑洁','客服部','中国大陆','管理人员','M3','正式','在职');
INSERT INTO employee_directory VALUES ('E008','冯军','信息技术部','中国大陆','管理人员','M5','正式','在职');
INSERT INTO employee_directory VALUES ('E009','许静','合规部','中国大陆','管理人员','M4','正式','在职');
INSERT INTO employee_directory VALUES ('E010','罗志成','销售部','华南区','区域负责人','M4','正式','在职');
INSERT INTO employee_directory VALUES ('E011','梁诗琪','运营部','华东区','区域负责人','M4','正式','在职');
INSERT INTO employee_directory VALUES ('E012','林晓芳','财务部','华南区','财务人员','P5','正式','在职');
INSERT INTO employee_directory VALUES ('E013','穆勒','销售部','欧洲','区域负责人','M4','正式','在职');
INSERT INTO employee_directory VALUES ('E014','约翰逊','销售部','北美','区域负责人','M4','正式','在职');
INSERT INTO employee_directory VALUES ('E015','周凯','运营部','华东区','管理人员','M3','正式','在职');
INSERT INTO employee_directory VALUES ('E020','刘洋','运营部','中国大陆','管理人员','M2','正式','在职');
INSERT INTO employee_directory VALUES ('E023','王磊','财务部','中国大陆','财务人员','P4','正式','在职');
INSERT INTO employee_directory VALUES ('E037','张伟','销售部','华南区','普通员工','P3','正式','在职');
INSERT INTO employee_directory VALUES ('E044','杜鹏','运营部','华南区','普通员工','P3','正式','离职');
INSERT INTO employee_directory VALUES ('E052','高翔','运营部','华东区','普通员工','P4','正式','在职');
INSERT INTO employee_directory VALUES ('E058','李静','财务部','中国大陆','管理人员','M5','正式','在职');
INSERT INTO employee_directory VALUES ('E060','艾米丽','客服部','华东区','外包人员','P1','外包','在职');
INSERT INTO employee_directory VALUES ('E061','韩梅','人力资源部','中国大陆','实习生','I1','实习','在职');
INSERT INTO employee_directory VALUES ('E016','林海燕','采购部','华东区','普通员工','P2','正式','在职');
INSERT INTO employee_directory VALUES ('E017','黄浩然','人力资源部','华北区','普通员工','P3','正式','在职');
INSERT INTO employee_directory VALUES ('E018','张丽娜','法务部','中国大陆','普通员工','P4','正式','在职');
INSERT INTO employee_directory VALUES ('E019','吴勇军','销售部','中国香港','普通员工','P5','正式','在职');
INSERT INTO employee_directory VALUES ('E021','李凤英','运营部','东南亚','普通员工','P1','正式','在职');
INSERT INTO employee_directory VALUES ('E022','王国强','客服部','欧洲','管理人员','M3','正式','在职');
INSERT INTO employee_directory VALUES ('E024','刘静怡','信息技术部','华南区','采购人员','P4','正式','在职');
INSERT INTO employee_directory VALUES ('E025','杨天宇','合规部','华东区','外包人员','P2','外包','在职');
INSERT INTO employee_directory VALUES ('E026','赵桂英','财务部','华北区','实习生','I1','实习','在职');
INSERT INTO employee_directory VALUES ('E027','周德海','采购部','中国大陆','普通员工','P1','正式','在职');
INSERT INTO employee_directory VALUES ('E028','徐秀英','人力资源部','中国香港','普通员工','P2','正式','在职');
INSERT INTO employee_directory VALUES ('E029','孙俊杰','法务部','东南亚','普通员工','P3','正式','在职');
INSERT INTO employee_directory VALUES ('E030','马淑芬','销售部','欧洲','普通员工','P4','正式','在职');
INSERT INTO employee_directory VALUES ('E031','朱子轩','运营部','华南区','普通员工','P5','正式','在职');
INSERT INTO employee_directory VALUES ('E032','胡秀兰','客服部','华东区','普通员工','P1','正式','在职');
INSERT INTO employee_directory VALUES ('E033','郭志刚','信息技术部','华北区','管理人员','M1','正式','在职');
INSERT INTO employee_directory VALUES ('E034','何玉华','合规部','中国大陆','采购人员','P4','正式','在职');
INSERT INTO employee_directory VALUES ('E035','高志强','财务部','中国香港','外包人员','P2','外包','在职');
INSERT INTO employee_directory VALUES ('E036','罗雪梅','采购部','东南亚','实习生','I1','实习','在职');
INSERT INTO employee_directory VALUES ('E038','郑志远','人力资源部','欧洲','普通员工','P1','正式','在职');
INSERT INTO employee_directory VALUES ('E039','梁玉梅','法务部','华南区','普通员工','P2','正式','在职');
INSERT INTO employee_directory VALUES ('E040','谢立新','销售部','华东区','普通员工','P3','正式','在职');
INSERT INTO employee_directory VALUES ('E041','宋晓芳','运营部','华北区','普通员工','P4','正式','在职');
INSERT INTO employee_directory VALUES ('E042','唐文博','客服部','中国大陆','普通员工','P5','正式','在职');
INSERT INTO employee_directory VALUES ('E043','许玉兰','信息技术部','中国香港','普通员工','P1','正式','在职');
INSERT INTO employee_directory VALUES ('E045','韩伟东','合规部','东南亚','管理人员','M3','正式','在职');
INSERT INTO employee_directory VALUES ('E046','冯红梅','财务部','欧洲','财务人员','P4','正式','在职');
INSERT INTO employee_directory VALUES ('E047','邓永强','采购部','华南区','外包人员','P2','外包','在职');
INSERT INTO employee_directory VALUES ('E048','曹丽华','人力资源部','华东区','实习生','I1','实习','在职');
INSERT INTO employee_directory VALUES ('E049','彭嘉豪','法务部','华北区','普通员工','P1','正式','在职');
INSERT INTO employee_directory VALUES ('E050','陈春兰','销售部','中国大陆','普通员工','P2','正式','在职');
INSERT INTO employee_directory VALUES ('E051','林鑫磊','运营部','中国香港','普通员工','P3','正式','在职');
INSERT INTO employee_directory VALUES ('E053','黄银花','客服部','东南亚','普通员工','P4','正式','在职');
INSERT INTO employee_directory VALUES ('E054','张建军','信息技术部','欧洲','普通员工','P5','正式','在职');
INSERT INTO employee_directory VALUES ('E055','吴雅琴','合规部','华南区','普通员工','P1','正式','在职');
INSERT INTO employee_directory VALUES ('E056','李建国','财务部','华东区','管理人员','M1','正式','在职');
INSERT INTO employee_directory VALUES ('E057','王慧敏','采购部','华北区','采购人员','P4','正式','在职');
