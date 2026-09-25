/**
 * Giọng hệ thống của CosyVoice v2 và v3 Flash, theo danh sách giọng chính thức của Alibaba (tài khoản Trung Quốc, xem
 * ngày 2026-09-25). Chỉ giữ giọng nói được tiếng Anh, vì Companion trả lời bằng tiếng Anh; mô tả dịch từ cột đặc điểm
 * của Alibaba. AIRI dùng CosyVoice v1, ngừng chạy ngày 2026-10-10; 18 trong 20 giọng của nó có ở v2 với đuôi `_v2`
 * (thiếu 龙彤, 龙祥), 14 giọng có ở v3 Flash với đuôi `_v3`.
 */
import type { VoiceOption } from "./voiceProviders";

/** Tên hiện trong bảng chọn: tên tiếng Trung kèm phiên âm lấy từ mã giọng ("龙婉 · Long Wan"), hay tên Latin sẵn có. */
function voiceLabel(id: string, name: string): string {
  const base = id.replace(/_v\d+$/, "");
  if (base.startsWith("loong")) return base.charAt(5).toUpperCase() + base.slice(6);
  if (!/[\u4e00-\u9fff]/.test(name)) return name;
  const roman = base === "libai" ? "Li Bai"
    : base.startsWith("long") ? `Long ${base.charAt(4).toUpperCase()}${base.slice(5)}`
    : base.charAt(0).toUpperCase() + base.slice(1);
  return `${name} · ${roman}`;
}

function grouped(group: string, rows: [id: string, name: string, hint: string][]): VoiceOption[] {
  return rows.map(([id, name, hint]) => ({ id, label: voiceLabel(id, name), hint, group }));
}

/** 100 giọng CosyVoice v2 nói được tiếng Anh. */
export const COSYVOICE_V2: VoiceOption[] = [
  ...grouped("Bầu bạn", [
    ["longanqin", "龙安亲", "Nữ · thân thiện, hoạt bát"],
    ["longanya", "龙安雅", "Nữ · thanh cao, có khí chất"],
    ["longanshuo", "龙安朔", "Nam · trong trẻo, tươi mát"],
    ["longanling", "龙安灵", "Nữ · nhanh nhạy, linh hoạt"],
    ["longanzhi", "龙安智", "Nam · sáng suốt, chín chắn"],
    ["longanrou", "龙安柔", "Nữ · dịu dàng như bạn thân"],
    ["longqiang_v2", "龙嫱", "Nữ · lãng mạn, quyến rũ"],
    ["longhan_v2", "龙寒", "Nam · ấm áp, si tình"],
    ["longxing_v2", "龙星", "Nữ · dịu dàng, cô gái nhà bên"],
    ["longhua_v2", "龙华", "Nữ · ngọt ngào, tràn năng lượng"],
    ["longwan_v2", "龙婉", "Nữ · tích cực, trí thức"],
    ["longcheng_v2", "龙橙", "Nam · thanh niên thông minh"],
    ["longfeifei_v2", "龙菲菲", "Nữ · ngọt ngào, nhõng nhẽo"],
    ["longxiaocheng_v2", "龙小诚", "Nam · trầm, cuốn hút"],
    ["longzhe_v2", "龙哲", "Nam · hơi vụng, ấm áp"],
    ["longyan_v2", "龙颜", "Nữ · ấm như gió xuân"],
    ["longtian_v2", "龙天", "Nam · trầm, lý trí"],
    ["longze_v2", "龙泽", "Nam · ấm áp, tràn năng lượng"],
    ["longshao_v2", "龙邵", "Nam · tích cực, cầu tiến"],
    ["longhao_v2", "龙浩", "Nam · đa tình, u buồn"],
    ["kabuleshen_v2", "龙深", "Nam · giọng ca sĩ"],
  ]),
  ...grouped("Trẻ em", [
    ["longhuhu", "龙呼呼", "Bé gái · hồn nhiên"],
    ["longwangwang", "龙汪汪", "Bé trai · thiếu niên Đài Loan"],
    ["longpaopao", "龙泡泡", "Trẻ em · như bong bóng bay"],
    ["longshanshan", "龙闪闪", "Trẻ em · giàu kịch tính"],
    ["longniuniu", "龙牛牛", "Bé trai · tươi sáng"],
    ["longjielidou_v2", "龙杰力豆", "Bé trai · tươi sáng, nghịch ngợm"],
    ["longling_v2", "龙铃", "Bé gái · ngây ngô, hơi cứng"],
    ["longke_v2", "龙可", "Bé gái · ngây thơ, ngoan"],
    ["longxian_v2", "龙仙", "Bé gái · phóng khoáng, đáng yêu"],
  ]),
  ...grouped("Trợ lý", [
    ["longanli", "龙安莉", "Nữ · gọn gàng, điềm đạm"],
    ["longanlang", "龙安朗", "Nam · tươi mát, gọn gàng"],
    ["longanwen", "龙安温", "Nữ · thanh lịch, trí thức"],
    ["longanyun", "龙安昀", "Nam · ấm áp, của gia đình"],
    ["longyumi_v2", "YUMI", "Nữ · trẻ, nghiêm túc"],
    ["longxiaochun_v2", "龙小淳", "Nữ · trí thức, tích cực"],
    ["longxiaoxia_v2", "龙小夏", "Nữ · điềm tĩnh, uy quyền"],
    ["longanpei", "龙安培", "Nữ · cô giáo cho tuổi teen"],
  ]),
  ...grouped("Đọc truyện", [
    ["longyichen", "龙逸尘", "Nam · phóng khoáng, năng động"],
    ["longwanjun", "龙婉君", "Nữ · tinh tế, giọng mềm"],
    ["longlaobo", "龙老伯", "Ông · từng trải, phong sương"],
    ["longlaoyi", "龙老姨", "Dì · đời thường, điềm đạm"],
    ["longbaizhi", "龙白芷", "Nữ · dẫn chuyện sắc sảo"],
    ["longsanshu", "龙三叔", "Nam · điềm tĩnh, giọng dày"],
    ["longxiu_v2", "龙修", "Nam · kể chuyện, uyên bác"],
    ["longmiao_v2", "龙妙", "Nữ · lên xuống có nhịp"],
    ["longyue_v2", "龙悦", "Nữ · ấm, trầm cuốn hút"],
    ["longnan_v2", "龙楠", "Nam · thanh niên sáng suốt"],
    ["longyuan_v2", "龙媛", "Nữ · ấm áp, chữa lành"],
  ]),
  ...grouped("Tin tức", [
    ["longshu_v2", "龙书", "Nam · thanh niên điềm tĩnh"],
    ["loongbella_v2", "Bella2.0", "Nữ · chuẩn xác, gọn gàng"],
    ["longshuo_v2", "龙硕", "Nam · uyên bác, gọn gàng"],
    ["longxiaobai_v2", "龙小白", "Nữ · đọc tin điềm tĩnh"],
    ["longjing_v2", "龙婧", "Nữ · giọng phát thanh viên"],
    ["loongstella_v2", "loongstella", "Nữ · dứt khoát, nhanh nhẹn"],
  ]),
  ...grouped("Ngâm thơ", [
    ["longfei_v2", "龙飞", "Nam · nhiệt huyết, trầm cuốn hút"],
    ["libai_v2", "李白", "Nam · thi tiên thời xưa"],
    ["longjin_v2", "龙津", "Nam · nho nhã, ấm áp"],
  ]),
  ...grouped("Lồng tiếng video", [
    ["longjiqi", "龙机器", "Người máy ngơ ngác, dễ thương"],
    ["longhouge", "龙猴哥", "Nam · Tôn Ngộ Không kinh điển"],
    ["longjixin", "龙机心", "Nữ · đanh đá, mưu mẹo"],
    ["longanyue", "龙安粤", "Nam · vui nhộn · tiếng Quảng Đông"],
    ["longshange", "龙陕哥", "Nam · chất Thiểm Bắc · tiếng Thiểm Tây"],
    ["longanmin", "龙安敏", "Nữ · ngọt ngào · tiếng Mân Nam"],
    ["longdaiyu", "龙黛玉", "Nữ · tài nữ, kiêu và thẳng"],
    ["longgaoseng", "龙高僧", "Nam · cao tăng đắc đạo"],
  ]),
  ...grouped("Phương ngữ", [
    ["longlaotie_v2", "龙老铁", "Nam · thẳng tính · giọng Đông Bắc"],
    ["longjiayi_v2", "龙嘉怡", "Nữ · trí thức · tiếng Quảng Đông"],
    ["longtao_v2", "龙桃", "Nữ · tích cực · tiếng Quảng Đông"],
  ]),
  ...grouped("Tiếng Anh bản xứ", [
    ["loongeva_v2", "loongeva", "Nữ · trí thức · chỉ tiếng Anh-Anh"],
    ["loongbrian_v2", "loongbrian", "Nam · điềm tĩnh · chỉ tiếng Anh-Anh"],
    ["loongluna_v2", "loongluna", "Nữ · chỉ tiếng Anh-Anh"],
    ["loongluca_v2", "loongluca", "Nam · chỉ tiếng Anh-Anh"],
    ["loongemily_v2", "loongemily", "Nữ · chỉ tiếng Anh-Anh"],
    ["loongeric_v2", "loongeric", "Nam · chỉ tiếng Anh-Anh"],
    ["loongabby_v2", "loongabby", "Nữ · chỉ tiếng Anh-Mỹ"],
    ["loongannie_v2", "loongannie", "Nữ · chỉ tiếng Anh-Mỹ"],
    ["loongandy_v2", "loongandy", "Nam · chỉ tiếng Anh-Mỹ"],
    ["loongava_v2", "loongava", "Nữ · chỉ tiếng Anh-Mỹ"],
    ["loongbeth_v2", "loongbeth", "Nữ · chỉ tiếng Anh-Mỹ"],
    ["loongbetty_v2", "loongbetty", "Nữ · chỉ tiếng Anh-Mỹ"],
    ["loongcindy_v2", "loongcindy", "Nữ · chỉ tiếng Anh-Mỹ"],
    ["loongcally_v2", "loongcally", "Nữ · chỉ tiếng Anh-Mỹ"],
    ["loongdavid_v2", "loongdavid", "Nam · chỉ tiếng Anh-Mỹ"],
    ["loongdonna_v2", "loongdonna", "Nữ · chỉ tiếng Anh-Mỹ"],
  ]),
  ...grouped("Chăm sóc khách hàng", [
    ["longyingmu", "龙应沐", "Nữ · thanh lịch, trí thức"],
    ["longyingxun", "龙应询", "Nam · trẻ, còn non"],
    ["longyingcui", "龙应催", "Nam · nghiêm, kiểu nhắc nợ"],
    ["longyingda", "龙应答", "Nữ · vui tươi, giọng cao"],
    ["longyingjing", "龙应静", "Nữ · điềm tĩnh, nhẹ nhàng"],
    ["longyingyan", "龙应严", "Nữ · nghiêm, dứt khoát"],
    ["longyingtian", "龙应甜", "Nữ · dịu dàng, ngọt ngào"],
    ["longyingbing", "龙应冰", "Nữ · sắc, mạnh mẽ"],
    ["longyingtao", "龙应桃", "Nữ · dịu dàng, bình thản"],
    ["longyingling", "龙应聆", "Nữ · ôn hòa, thấu cảm"],
  ]),
  ...grouped("Bán hàng", [
    ["longyingxiao", "龙应笑", "Nữ · ngọt, kiểu chào hàng"],
    ["longanran", "龙安燃", "Nữ · hoạt bát, giọng dày"],
    ["longanxuan", "龙安宣", "Nữ · giọng livestream kinh điển"],
    ["longanchong", "龙安冲", "Nam · hăng hái chào hàng"],
    ["longanping", "龙安萍", "Nữ · livestream, giọng cao vút"],
  ]),
];

/** 80 giọng CosyVoice v3 Flash nói được tiếng Anh. */
export const COSYVOICE_V3_FLASH: VoiceOption[] = [
  ...grouped("Bầu bạn", [
    ["longanyang", "龙安洋", "Nam · chàng trai tươi sáng · 20–30 tuổi"],
    ["longanhuan_v3", "龙安欢 V3", "Nữ · vui nhộn, tràn năng lượng · nói được 8 phương ngữ · 20–30 tuổi"],
    ["longanhuan", "龙安欢", "Nữ · vui nhộn, tràn năng lượng · 20–30 tuổi"],
    ["longantai_v3", "龙安台", "Nữ · ngọt, nũng nịu kiểu Đài Loan · 20–25 tuổi"],
    ["longhua_v3", "龙华", "Nữ · ngọt ngào, tràn năng lượng · 20–25 tuổi"],
    ["longcheng_v3", "龙橙", "Nam · thanh niên thông minh · 20–25 tuổi"],
    ["longze_v3", "龙泽", "Nam · ấm áp, tràn năng lượng · 25–30 tuổi"],
    ["longzhe_v3", "龙哲", "Nam · hơi vụng, ấm áp · 25–30 tuổi"],
    ["longyan_v3", "龙颜", "Nữ · ấm như gió xuân · 30–35 tuổi"],
    ["longxing_v3", "龙星", "Nữ · dịu dàng, cô gái nhà bên · 20–25 tuổi"],
    ["longtian_v3", "龙天", "Nam · trầm, lý trí · 30–35 tuổi"],
    ["longwan_v3", "龙婉", "Nữ · tinh tế, giọng mềm · 20–30 tuổi"],
    ["longqiang_v3", "龙嫱", "Nữ · lãng mạn, quyến rũ · 30–35 tuổi"],
    ["longfeifei_v3", "龙菲菲", "Nữ · ngọt ngào, nhõng nhẽo · 20–25 tuổi"],
    ["longhao_v3", "龙浩", "Nam · đa tình, u buồn · 30–35 tuổi"],
    ["longanrou_v3", "龙安柔", "Nữ · dịu dàng như bạn thân · 20–35 tuổi"],
    ["longhan_v3", "龙寒", "Nam · ấm áp, si tình · 30–35 tuổi"],
    ["longanzhi_v3", "龙安智", "Nam · sáng suốt, chín chắn · 25–35 tuổi"],
    ["longanling_v3", "龙安灵", "Nữ · nhanh nhạy, linh hoạt · 20–30 tuổi"],
    ["longanya_v3", "龙安雅", "Nữ · thanh cao, có khí chất · 25–35 tuổi"],
    ["longanqin_v3", "龙安亲", "Nữ · thân thiện, hoạt bát · 20–25 tuổi"],
  ]),
  ...grouped("Trẻ em", [
    ["longhuhu_v3", "龙呼呼", "Bé gái · hồn nhiên · 6–10 tuổi"],
    ["longpaopao_v3", "龙泡泡", "Trẻ em · như bong bóng bay · 6–15 tuổi"],
    ["longjielidou_v3", "龙杰力豆", "Bé trai · tươi sáng, nghịch ngợm · 10 tuổi"],
    ["longxian_v3", "龙仙", "Bé gái · phóng khoáng, đáng yêu · 12 tuổi"],
    ["longling_v3", "龙铃", "Bé gái · ngây ngô, hơi cứng · 10 tuổi"],
    ["longshanshan_v3", "龙闪闪", "Trẻ em · giàu kịch tính · 6–15 tuổi"],
    ["longniuniu_v3", "龙牛牛", "Bé trai · tươi sáng · 6–15 tuổi"],
  ]),
  ...grouped("Trợ lý", [
    ["longxiaochun_v3", "龙小淳", "Nữ · trí thức, tích cực · 25–30 tuổi"],
    ["longxiaoxia_v3", "龙小夏", "Nữ · điềm tĩnh, uy quyền · 25–30 tuổi"],
    ["longyumi_v3", "YUMI", "Nữ · trẻ, nghiêm túc · 20–25 tuổi"],
    ["longanyun_v3", "龙安昀", "Nam · ấm áp, của gia đình · 30–35 tuổi"],
    ["longanwen_v3", "龙安温", "Nữ · thanh lịch, trí thức · 25–35 tuổi"],
    ["longanli_v3", "龙安莉", "Nữ · gọn gàng, điềm đạm · 25–35 tuổi"],
    ["longanlang_v3", "龙安朗", "Nam · tươi mát, gọn gàng · 20–25 tuổi"],
    ["longyingmu_v3", "龙应沐", "Nữ · thanh lịch, trí thức · 25–30 tuổi"],
  ]),
  ...grouped("Đọc truyện", [
    ["longmiao_v3", "龙妙", "Nữ · lên xuống có nhịp · 25–30 tuổi"],
    ["longsanshu_v3", "龙三叔", "Nam · điềm tĩnh, giọng dày · 25–45 tuổi"],
    ["longyuan_v3", "龙媛", "Nữ · ấm áp, chữa lành · 35–40 tuổi"],
    ["longyue_v3", "龙悦", "Nữ · ấm, trầm cuốn hút · 30–35 tuổi"],
    ["longxiu_v3", "龙修", "Nam · kể chuyện, uyên bác · 25–35 tuổi"],
    ["longnan_v3", "龙楠", "Nam · thanh niên sáng suốt · 25–30 tuổi"],
    ["longwanjun_v3", "龙婉君", "Nữ · tinh tế, giọng mềm · 20–30 tuổi"],
    ["longyichen_v3", "龙逸尘", "Nam · phóng khoáng, năng động · 20–30 tuổi"],
    ["longlaobo_v3", "龙老伯", "Ông · từng trải, phong sương · trên 60 tuổi"],
    ["longlaoyi_v3", "龙老姨", "Dì · đời thường, điềm đạm · trên 60 tuổi"],
  ]),
  ...grouped("Tin tức", [
    ["longshuo_v3", "龙硕", "Nam · uyên bác, gọn gàng · 25–30 tuổi"],
    ["longshu_v3", "龙书", "Nam · thanh niên điềm tĩnh · 20–25 tuổi"],
    ["loongbella_v3", "Bella3.0", "Nữ · chuẩn xác, gọn gàng · 25–30 tuổi"],
  ]),
  ...grouped("Ngâm thơ", [
    ["longfei_v3", "龙飞", "Nam · nhiệt huyết, trầm cuốn hút · 30–35 tuổi"],
  ]),
  ...grouped("Lồng tiếng video", [
    ["longjiqi_v3", "龙机器", "Người máy ngơ ngác, dễ thương · 20–30 tuổi"],
    ["longhouge_v3", "龙猴哥", "Nam · Tôn Ngộ Không kinh điển · 20–25 tuổi"],
    ["longdaiyu_v3", "龙黛玉", "Nữ · tài nữ, kiêu và thẳng · 15–25 tuổi"],
  ]),
  ...grouped("Phương ngữ", [
    ["longjiaxin_v3", "龙嘉欣", "Nữ · thanh lịch · tiếng Quảng Đông · 30–35 tuổi"],
    ["longjiayi_v3", "龙嘉怡", "Nữ · trí thức · tiếng Quảng Đông · 25–30 tuổi"],
    ["longanyue_v3", "龙安粤", "Nam · vui nhộn · tiếng Quảng Đông · 25–35 tuổi"],
    ["longlaotie_v3", "龙老铁", "Nam · thẳng tính · giọng Đông Bắc · 25–30 tuổi"],
    ["longshange_v3", "龙陕哥", "Nam · chất Thiểm Bắc · tiếng Thiểm Tây · 25–35 tuổi"],
    ["longanmin_v3", "龙安闽", "Nữ · thiếu nữ trong sáng · tiếng Mân Nam · 18–25 tuổi"],
  ]),
  ...grouped("Tiếng Anh bản xứ", [
    ["loongabby_v3", "loongabby", "Nữ · chỉ tiếng Anh-Mỹ · 30–35 tuổi"],
    ["loongandy_v3", "loongandy", "Nam · chỉ tiếng Anh-Mỹ · 30–35 tuổi"],
    ["loongannie_v3", "loongannie", "Nữ · chỉ tiếng Anh-Mỹ · 30–35 tuổi"],
    ["loongava_v3", "loongava", "Nữ · chỉ tiếng Anh-Mỹ · 35–40 tuổi"],
    ["loongbeth_v3", "loongbeth", "Nữ · chỉ tiếng Anh-Mỹ · 35–40 tuổi"],
    ["loongbetty_v3", "loongbetty", "Nữ · chỉ tiếng Anh-Mỹ · 35–40 tuổi"],
    ["loongcally_v3", "loongcally", "Nữ · chỉ tiếng Anh-Mỹ · 25–30 tuổi"],
    ["loongcindy_v3", "loongcindy", "Nữ · chỉ tiếng Anh-Mỹ · 30–35 tuổi"],
    ["loongdavid_v3", "loongdavid", "Nam · chỉ tiếng Anh-Mỹ · 35–40 tuổi"],
    ["loongdonna_v3", "loongdonna", "Nữ · chỉ tiếng Anh-Mỹ · 35–40 tuổi"],
    ["loongemily_v3", "loongemily", "Nữ · chỉ tiếng Anh-Anh · 35–40 tuổi"],
    ["loongeric_v3", "loongeric", "Nam · chỉ tiếng Anh-Anh · 35–40 tuổi"],
    ["loongluna_v3", "loongluna", "Nữ · chỉ tiếng Anh-Anh · 35–40 tuổi"],
    ["loongluca_v3", "loongluca", "Nam · chỉ tiếng Anh-Anh · 25–30 tuổi"],
  ]),
  ...grouped("Chăm sóc khách hàng", [
    ["longyingxun_v3", "龙应询", "Nam · trẻ, còn non · 20–25 tuổi"],
    ["longyingjing_v3", "龙应静", "Nữ · điềm tĩnh, nhẹ nhàng · 25–35 tuổi"],
    ["longyingling_v3", "龙应聆", "Nữ · ôn hòa, thấu cảm · 25–30 tuổi"],
    ["longyingtao_v3", "龙应桃", "Nữ · dịu dàng, bình thản · 25–30 tuổi"],
  ]),
  ...grouped("Bán hàng", [
    ["longyingxiao_v3", "龙应笑", "Nữ · ngọt, kiểu chào hàng · 20–25 tuổi"],
    ["longanran_v3", "龙安燃", "Nữ · hoạt bát, giọng dày · 30–40 tuổi"],
    ["longanxuan_v3", "龙安宣", "Nữ · giọng livestream kinh điển · 30–40 tuổi"],
  ]),
];
