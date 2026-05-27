# Chinese Military Systems - Official Translations (标准中译名)
# Sources: PLA official media (国防部, 央视军事, 解放军报), state media (新华社),
#          military export catalogs (CASC, CASIC, NORINCO, AVIC)

# ============================================================
# CHINESE MISSILES & AIRCRAFT (中国导弹与飞机)
# ============================================================

air_to_air = {
    # 霹雳 (PL) series - PLAAF standard AAM family
    'PL-5':       '霹雳-5',
    'PL-7':       '霹雳-7',
    'PL-8':       '霹雳-8',
    'PL-9':       '霹雳-9',
    'PL-10':      '霹雳-10',
    'PL-11':      '霹雳-11',
    'PL-12':      '霹雳-12',     # aka SD-10 export designation
    'SD-10':      'SD-10',       # export name for PL-12
    'PL-15':      '霹雳-15',
    'PL-17':      '霹雳-17',
    'PL-21':      '霹雳-21',
    'PL-XX':      '霹雳-XX',     #下一代空对空导弹
    'TY-90':      '天燕-90',     # helicopter AAM
}

surface_to_air = {
    # 红旗 (HQ) series - primary PLAAF SAM family
    'HQ-7':       '红旗-7',
    'HQ-9':       '红旗-9',
    'HQ-16':      '红旗-16',
    'HQ-17':      '红旗-17',
    'HQ-22':      '红旗-22',
    'HQ-61':      '红旗-61',
    'HQ-64':      '红旗-64',     # improved HQ-61
    'HQ-89':      '红旗-89',     # export variant designation
    'HQ-19':      '红旗-19',     # exo-atmospheric interceptor
    'HQ-26':      '红旗-26',     # naval long-range SAM (speculative designation)
    'HQ-29':      '红旗-29',     # short-range SAM (speculative designation)

    # 地空 (DK) series
    'DK-1':       '地空-1',
    'DK-9':       '地空-9',

    # 凯山 (KS) series
    'KS-1':       '凯山-1',
    'KS-1A':      '凯山-1A',
    'KS-1C':      '凯山-1C',

    # 猎鹰 (LY) export series
    'LY-60':      '猎鹰-60',

    # 飞豹 (FB) series
    'FB-10':      '飞豹-10',
    'FB-6A':      '飞豹-6A',
    'FL-2000V':   '飞獴-2000V',  # Flying Mantis

    # 前卫 (QW) MANPADS
    'QW-1':       '前卫-1',
    'QW-2':       '前卫-2',
    'QW-3':       '前卫-3',
    'QW-11':      '前卫-11',
    'QW-18':      '前卫-18',

    # 飞弩 (FN) MANPADS
    'FN-6':       '飞弩-6',

    # 红缨 (HN) MANPADS
    'HN-5':       '红缨-5',
    'HN-6':       '红缨-6',

    # HQ-17 subvariants
    'HQ-17A':     '红旗-17A',
    'HQ-17AE':    '红旗-17AE',   # export variant
}

anti_ship = {
    # 鹰击 (YJ) series - primary AShM family
    'YJ-8':       '鹰击-8',
    'YJ-81':      '鹰击-81',
    'YJ-82':      '鹰击-82',
    'YJ-62':      '鹰击-62',
    'YJ-83':      '鹰击-83',
    'YJ-91':      '鹰击-91',     # also anti-radiation variant
    'YJ-100':     '鹰击-100',
    'YJ-12':      '鹰击-12',
    'YJ-18':      '鹰击-18',
    'YJ-21':      '鹰击-21',

    # Export designations (CM = China Missile, C series)
    'CM-302':     'CM-302',      # export YJ-12

    # 海鹰 (HY) series - coastal defense
    'HY-1':       '海鹰-1',
    'HY-2':       '海鹰-2',
    'HY-3':       '海鹰-3',
    'HY-4':       '海鹰-4',

    # 天雷 (TL) series
    'TL-10B':     'TL-10B',
    'TL-6':       'TL-6',
    'TL-20':      'TL-20',
}

land_attack_cruise = {
    # 长剑 (CJ) series - primary LACM family
    'CJ-10':      '长剑-10',
    'CJ-20':      '长剑-20',
    'CJ-100':     '长剑-100',

    # 东海 (DH) series
    'DH-10':      '东海-10',     # earlier designation for CJ-10

    # 红鸟 (HN) series
    'HN-1':       '红鸟-1',
    'HN-2':       '红鸟-2',
    'HN-3':       '红鸟-3',

    # Others
    'K/AKD-88':   'K/AKD-88',    # air-launched cruise missile
    'CF-105':     'CF-105',      # cruise missile (CX-1衍生)
}

# Note: YJ-100 appears in both anti-ship and LACM contexts

ballistic = {
    # 东风 (DF) series - strategic/tactical ballistic missiles
    'DF-1':       '东风-1',
    'DF-2':       '东风-2',
    'DF-3':       '东风-3',
    'DF-4':       '东风-4',
    'DF-5':       '东风-5',
    'DF-5B':      '东风-5B',
    'DF-5C':      '东风-5C',
    'DF-11':      '东风-11',
    'DF-15':      '东风-15',
    'DF-16':      '东风-16',
    'DF-17':      '东风-17',
    'DF-21':      '东风-21',
    'DF-21D':     '东风-21D',    # carrier killer
    'DF-26':      '东风-26',
    'DF-31':      '东风-31',
    'DF-31AG':    '东风-31AG',
    'DF-41':      '东风-41',
    'DF-100':     '东风-100',    # formerly CJ-100

    # 巨浪 (JL) series - submarine-launched
    'JL-1':       '巨浪-1',
    'JL-2':       '巨浪-2',
    'JL-3':       '巨浪-3',

    # Tactical/export SRBMs
    'B-611':      'B-611',
    'M-7':        'M-7',
    'M-9':        'M-9',
    'M-11':       'M-11',
    'M-18':       'M-18',
    'M-20':       'M-20',
    'SY-400':     'SY-400',
    'CX-1':       'CX-1',
    'BP-12':      'BP-12',
    'P-12':       'P-12',
    'B-611M':     'B-611M',
}

anti_tank = {
    # 红箭 (HJ) series - primary ATGM family
    'HJ-8':       '红箭-8',
    'HJ-9':       '红箭-9',
    'HJ-10':      '红箭-10',
    'HJ-11':      '红箭-11',
    'HJ-12':      '红箭-12',
    'HJ-73':      '红箭-73',
    'HJ-16':      '红箭-16',

    # AF series - NORINCO export ATGMs
    'AFJ-02':     'AFJ-02',
    'AFT-07':     'AFT-07',
    'AFT-08':     'AFT-08',
    'AFT-09':     'AFT-09',      # export HJ-9
    'AFT-10':     'AFT-10',      # export HJ-10
    'AFT-11':     'AFT-11',
}

anti_radiation = {
    'YJ-91':      '鹰击-91',     # anti-radiation variant (Kh-31P copy)
    'LD-10':      'LD-10',       # anti-radiation missile
    'CM-102':     'CM-102',      # anti-radiation missile
    'AKF-98A':    'AKF-98A',     # air-launched decoy/ARM
}

air_to_surface = {
    # 鹰击 series (air-launched anti-ship)
    'YJ-61':      '鹰击-61',
    'YJ-9':       '鹰击-9',
    'YJ-9E':      '鹰击-9E',
    'YJ-83K':     '鹰击-83K',
    'YJ-83KH':    '鹰击-83KH',

    # 空地 (KD) series
    'KD-88':      '空地-88',
    'K/AKD-88':   'K/AKD-88',    # same as above

    # Other ASMs
    'KD-63':      '空地-63',     # air-launched cruise

    # CM export series
    'CM-102':     'CM-102',
    'CM-506':     'CM-506',      # small guided bomb

    # AKF series (air-launched
    'AKF-98':     'AKF-98',
    'AKF-88':     'AKF-88',
    'AKF-98A':    'AKF-98A',

    # 雷石 (LS) series - guided bombs
    'LS-6':       '雷石-6',

    # 天戈 (TG) series
    'TG-100':     '天戈-100',

    # Others
    'TF-2000':    'TF-2000',

    # 云箭 (YZ) series
    'YZ-100':     '云箭-100',
    'YZ-200':     '云箭-200',
    'YZ-81':      '云箭-81',

    # TL series
    'TL-20':      'TL-20',
    'TL-30':      'TL-30',

    'BRM1':       'BRM1',

    # 飞腾 (FT) series - GPS/INS guided bombs
    'FT-1':       '飞腾-1',
    'FT-2':       '飞腾-2',
    'FT-3':       '飞腾-3',
    'FT-4':       '飞腾-4',
    'FT-5':       '飞腾-5',
    'FT-6':       '飞腾-6',
    'FT-7':       '飞腾-7',
    'FT-9':       '飞腾-9',
    'FT-10':      '飞腾-10',
    'FT-12':      '飞腾-12',

    # GB series (guided bombs)
    'GB-1':       'GB-1',        # 500kg laser guided bomb
    'GB-2':       'GB-2',        # 250kg
    'GB-3':       'GB-3',
    'GB-4':       'GB-4',
    'GB-5':       'GB-5',
    'GB-6':       'GB-6',
    'GB-9':       'GB-9',

    # 云雷 (YL) series - guided bombs/missiles
    'YL-1':       '云雷-1',
    'YL-2':       '云雷-2',
    'YL-3':       '云雷-3',
    'YL-4':       '云雷-4',
    'YL-5':       '云雷-5',
    'YL-6':       '云雷-6',
    'YL-7':       '云雷-7',
    'YL-8':       '云雷-8',
    'YL-9':       '云雷-9',
    'YL-10':      '云雷-10',
    'YL-11':      '云雷-11',
    'YL-12':      '云雷-12',
    'YL-13':      '云雷-13',
    'YL-14':      '云雷-14',
    'YL-15':      '云雷-15',
}

# Note: MANPADS is covered in surface_to_air section
manpads = {
    'QW-1':       '前卫-1',
    'QW-2':       '前卫-2',
    'QW-3':       '前卫-3',
    'QW-11':      '前卫-11',
    'QW-18':      '前卫-18',
    'FN-6':       '飞弩-6',
    'HN-5':       '红缨-5',
    'HN-6':       '红缨-6',
    'TA-7':       'TA-7',
    'TA-10':      'TA-10',
}

aircraft = {
    # 歼 (J) series - fighters
    'J-7':        '歼-7',
    'J-8':        '歼-8',
    'J-8II':      '歼-8II',
    'J-10':       '歼-10',
    'J-10A':      '歼-10A',
    'J-10B':      '歼-10B',
    'J-10C':      '歼-10C',
    'J-11':       '歼-11',
    'J-11B':      '歼-11B',
    'J-11BS':     '歼-11BS',
    'J-15':       '歼-15',       # carrier-based
    'J-16':       '歼-16',
    'J-20':       '歼-20',       # 威龙 (Chengdu J-20)
    'J-31':       '歼-31',       # FC-31 / 鹘鹰
    'J-35':       '歼-35',       # carrier-based stealth fighter

    # 歼轰 (JH) series - fighter-bombers
    'JH-7':       '歼轰-7',      # 飞豹
    'JH-7A':      '歼轰-7A',
    'JH-7B':      '歼轰-7B',

    # 轰 (H) series - bombers
    'H-6':        '轰-6',
    'H-6K':       '轰-6K',       # 战神
    'H-6J':       '轰-6J',       # naval variant
    'H-6N':       '轰-6N',       # aerial refueling capable variant
    'H-20':       '轰-20',       # next-gen stealth bomber

    # 强 (Q) series - attack aircraft
    'Q-5':        '强-5',

    # 运 (Y) series - transports
    'Y-20':       '运-20',       # 鲲鹏
    'Y-20B':      '运-20B',
    'Y-9':        '运-9',
    'Y-8':        '运-8',

    # 空警 (KJ) series - AWACS
    'KJ-200':     '空警-200',    # 平衡木
    'KJ-2000':    '空警-2000',
    'KJ-500':     '空警-500',
    'KJ-600':     '空警-600',    # carrier-based AEW

    # 直 (Z) series - helicopters
    'Z-10':       '直-10',       # 霹雳火
    'Z-19':       '直-19',       # 黑旋风
    'Z-20':       '直-20',
    'Z-8':        '直-8',
    'Z-9':        '直-9',
    'Z-18':       '直-18',

    # 攻击 / 彩虹 (GJ/CH) series - UAVs
    'GJ-1':       '攻击-1',      # aka 彩虹-4
    'GJ-2':       '攻击-2',      # aka 彩虹-5
    'GJ-11':      '攻击-11',     # 利剑 stealth UCAV

    # 无侦 (WZ) series - reconnaissance UAVs
    'WZ-7':       '无侦-7',      # 翔龙
    'WZ-8':       '无侦-8',      # hypersonic recon drone
    'WZ-10':      '无侦-10',     # 彩虹-10 tiltrotor
    'WZ-2000':    '无侦-2000',

    # 彩虹 (CH) series - export UAVs
    'CH-3':       '彩虹-3',
    'CH-4':       '彩虹-4',
    'CH-5':       '彩虹-5',
    'CH-6':       '彩虹-6',
    'CH-7':       '彩虹-7',      # stealth flying wing

    # Other UAVs
    'TB-001':     'TB-001',      # 双尾蝎 twin-tailed
    'BZK-005':    'BZK-005',
    'BZK-007':    'BZK-007',
    'BZK-008':    'BZK-008',
    'BZK-009':    'BZK-009',
    'EA-03':      'EA-03',       # export WZ-7
    'ASN-206':    'ASN-206',
    'ASN-207':    'ASN-207',
    'ASN-209':    'ASN-209',

    # Recon variants
    'JZ-6':       '歼侦-6',
    'JZ-8':       '歼侦-8',

    # HY series drones
    'HY-1':       '海鹰-1',      # drone variant, not missile
}


# ============================================================
# RUSSIAN / UKRAINIAN SYSTEMS (俄罗斯/乌克兰)
# ============================================================

russian_srbm_irbm = {
    # Iskander family (9K720)
    '9K720':             '9K720',          # system designation
    '9K720 Iskander-M':  '伊斯坎德尔-M',
    '9K720 Iskander-K':  '伊斯坎德尔-K',
    '9K720 Iskander-E':  '伊斯坎德尔-E',
    '9M723':             '9M723',          # Iskander-M ballistic missile
    '9M728':             '9M728',          # Iskander-K cruise missile
    '9M729':             '9M729',          # Iskander extended-range cruise
    '9M730':             '9M730',          # Burevestnik nuclear cruise
    '9M731':             '9M731',
    '9M732':             '9M732',
    '9M733':             '9M733',
    '9M720':             '9M720',          # Iskander-M ballistic missile

    # Tochka
    '9M79':              '9M79',           # Tochka missile
    '9K79 Tochka':       '圆点',
    '9K79 Tochka-U':     '圆点-U',

    # Other SRBMs
    '9K52 Luna-M':       '月亮-M',
    'Luna-M':            '月亮-M',
    'TR-1 Temp':         '温度',
    'Temp':              '温度',
}

russian_sam = {
    # Tor (道尔) family
    '9K330 Tor':         '道尔',           # 9K330
    '9K331 Tor-M1':      '道尔-M1',
    '9K332 Tor-M2':      '道尔-M2',
    '9K332 Tor-M2U':     '道尔-M2U',
    'Tor-M2':            '道尔-M2',
    'Tor-M2U':           '道尔-M2U',
    '9K515 Tor-M2':      '道尔-M2',
    'Tor':               '道尔',

    # Buk (山毛榉) family
    '9K37 Buk':          '山毛榉',
    '9K317 Buk-M1':      '山毛榉-M1',
    '9K317 Buk-M2':      '山毛榉-M2',
    '9K317 Buk-M3':      '山毛榉-M3',
    'Buk-M3':            '山毛榉-M3',

    # S-300 family
    'S-300V':            'S-300V',
    'S-300VM':           'S-300VM',        # 安泰-2500
    'S-300V4':           'S-300V4',
    'S-300VMD':          'S-300VMD',
    'Antey-2500':        '安泰-2500',

    # S-350
    'S-350 Vityaz':      'S-350勇士',
    'Vityaz':            '勇士',

    # S-400
    'S-400 Triumf':      'S-400凯旋',
    'Triumf':            '凯旋',
    '48N6DM':            '48N6DM',         # S-400 missile
    '48N6E3':            '48N6E3',
    '40N6':              '40N6',
    '9M96E':             '9M96E',
    '9M96E2':            '9M96E2',

    # S-500
    'S-500 Prometheus':  'S-500普罗米修斯',
    'Prometheus':        '普罗米修斯',
    '77N6-N':            '77N6-N',
    '77N6-N1':           '77N6-N1',

    # Sosna-R
    'Sosna-R':           '索斯纳',

    # Pantsir (铠甲) family
    'Pantsir-S1':        '铠甲-S1',
    'Pantsir-S2':        '铠甲-S2',
    'Pantsir-SM':        '铠甲-SM',
    'Pantsir-SA':        '铠甲-SA',

    # Strela (箭) family
    'Strela-10M3':       '箭-10M3',
    'Strela-10MN':       '箭-10MN',

    # Osa
    'Osa-AKM':           '黄蜂-AKM',

    # Tunguska (通古斯卡)
    'Tunguska':          '通古斯卡',

    # MANPADS
    'Verba':             '柳树',           # 9K333
    '9K333 Verba':       '柳树',
    '9K38 Igla':         '针',
    'Igla':              '针',
    '9K310 Igla-1':      '针-1',
    'Igla-1':            '针-1',
    '9K338 Igla-S':      '针-S',
    'Igla-S':            '针-S',
    '9K32 Strela-2':     '箭-2',           # SA-7
    '9K36 Strela-3':     '箭-3',           # SA-14

    # Russian SAM radars
    '9S15M':             '9S15M',          # 雷达
    '9S19M':             '9S19M',
    '9S32M':             '9S32M',
    '96L6':              '96L6',
    '92N6':              '92N6',
    '92N2':              '92N2',
    '9S18M1':            '9S18M1',
    'Podlet-K1':         '副手-K1',
    'Podlet-K2':         '副手-K2',
    '1RS1-1E':           '1RS1-1E',
    '1RL123':            '1RL123',
}

russian_atgm = {
    # Metis (混血儿) family
    '9K115 Metis':       '混血儿',
    'Metis':             '混血儿',
    '9K115-2 Metis-M':   '混血儿-M',
    'Metis-M':           '混血儿-M',
    '9K115-3 Metis-M1':  '混血儿-M1',

    # Fagot/Konkurs (巴松管/竞赛) family
    '9K111 Fagot':       '巴松管',
    'Fagot':             '巴松管',
    '9K111-1 Konkurs':   '竞赛',
    'Konkurs':           '竞赛',
    '9K111-2 Konkurs-M': '竞赛-M',
    '9M113 Konkurs':     '竞赛',           # AT-5

    # Kornet (短号) family
    '9K135 Kornet':      '短号',
    'Kornet':            '短号',
    '9M133 Kornet-M':    '短号-M',
    '9M133 Kornet-EM':   '短号-EM',
    'Kornet-EM':         '短号-EM',
    '9M133F-1':          '9M133F-1',       # thermobaric
    '9M133F-2':          '9M133F-2',
    '9M133F-3':          '9M133F-3',

    # Bastion (堡垒) - AT-14
    '9K117 Bastion':     '堡垒',
    'Bastion':           '堡垒',           # AT-14
}

russian_naval = {
    # Kalibr (口径) family - 3M-54
    '3M-54 Kalibr':      '口径',
    'Kalibr':            '口径',
    '3M-54E':            '3M-54E',
    '3M-54E1':           '3M-54E1',
    '3M-54K':            '3M-54K',         # land attack
    '3M-54T':            '3M-54T',         # anti-ship
    '91RE1':             '91RE1',          # anti-submarine
    '91RE2':             '91RE2',

    # Zircon (锆石)
    '3M22 Zircon':       '锆石',
    'Zircon':            '锆石',

    # P-800 Oniks (缟玛瑙)
    'P-800 Oniks':       '缟玛瑙',
    'Oniks':             '缟玛瑙',
    'P-800 Yakhont':     '雅洪特',         # export name
    'Yakhont':           '雅洪特',
    '3M55':              '3M55',

    # Moskit (日炙)
    'P-270 Moskit':      '日炙',
    'Moskit':            '日炙',

    # Granit (花岗岩)
    'P-700 Granit':      '花岗岩',
    'Granit':            '花岗岩',

    # Vulkan (火山)
    'P-1000 Vulkan':     '火山',
    'Vulkan':            '火山',

    # Bazalt (玄武岩)
    'P-500 Bazalt':      '玄武岩',
    'Bazalt':            '玄武岩',

    # Termit (白蚁)
    'P-15 Termit':       '白蚁',
    'Termit':            '白蚁',

    # P-80 Zubr
    'P-80 Zubr':         'P-80',
}

russian_asm = {
    # Kh-59 (Ovod)
    'KH-59':             'Kh-59',
    'KH-59MK':           'Kh-59MK',
    'KH-59MK2':          'Kh-59MK2',
    'Kh-59M Ovod-M':     'Kh-59M',
    'KH-59MKM':          'Kh-59MKM',
    'Ovod':              'Ovod',

    # Kh-38
    'KH-38MLE':          'Kh-38MLE',
    'KH-38MAE':          'Kh-38MAE',
    'KH-38':             'Kh-38',

    # Kh-58 (anti-radiation)
    'KH-58':             'Kh-58',
    'KH-58A':            'Kh-58A',
    'KH-58E':            'Kh-58E',
    'KH-58UShKE':        'Kh-58UShKE',

    # Kh-31 (anti-radiation/anti-ship)
    'KH-31':             'Kh-31',
    'KH-31P':            'Kh-31P',         # anti-radiation
    'KH-31A':            'Kh-31A',         # anti-ship
    'KH-31PM':           'Kh-31PM',
    'KH-31AM':           'Kh-31AM',
    'KH-31PK':           'Kh-31PK',

    # Kh-35 (天王星)
    'KH-35':             'Kh-35',
    'KH-35U':            'Kh-35U',
    'KH-35E':            'Kh-35E',
    'KH-35V':            'Kh-35V',
    'Uran':              '天王星',
    'Uran-U':            '天王星-U',

    # Kh-36
    'KH-36':             'Kh-36',

    # Kh-47M2 Kinzhal (匕首)
    'KH-47M2 Kinzhal':   'Kh-47M2匕首',
    'Kinzhal':           '匕首',

    # Kh-55 / Kh-555 cruise
    'KH-55':             'Kh-55',
    'KH-55SM':           'Kh-55SM',
    'KH-555':            'Kh-555',
    'KH-55SE':           'Kh-55SE',

    # Kh-101 / Kh-102 cruise
    'KH-101':            'Kh-101',
    'KH-102':            'Kh-102',         # nuclear variant

    # Kh-50 / Kh-69 / Kh-BD / Kh-SD
    'KH-50':             'Kh-50',
    'KH-69':             'Kh-69',
    'KH-BD':             'Kh-BD',          # long-range AAM
    'Kh-SD':             'Kh-SD',
}

russian_misc = {
    # Burevestnik
    '9M730 Burevestnik': '海燕',           # nuclear-powered cruise missile
    'Burevestnik':       '海燕',

    # Status-6 / Poseidon
    'Status-6':          '波塞冬',         # nuclear torpedo/UUV
    'Poseidon':          '波塞冬',

    # GZUR
    'GZUR':              'GZUR',           # hypersonic missile project

    # Grom (雷霆) guided bombs
    'Grom-E1':           '雷霆-E1',
    'Grom-E2':           '雷霆-E2',

    # KAB series guided bombs
    'KAB-20':            'KAB-20',
    'KAB-250':           'KAB-250',
    'KAB-500S':          'KAB-500S',
    'KAB-500KR':         'KAB-500KR',
    'KAB-1500KR':        'KAB-1500KR',

    # UPAB glide bombs
    'UPAB-1500B':        'UPAB-1500B',
    'UPAB-500B':         'UPAB-500B',

    # BrahMos (joint India-Russia)
    'BrahMos':           '布拉莫斯',
}

russian_uav = {
    'Orion':             '猎户座',
    'Forpost':           '前哨',
    'Inokhodets':        '快步',           # Orion also called Inokhodets
    'Altius':            '牵牛星',
    'Okhotnik':          '猎人',
    'Okhotnik-B':        '猎人-B',
    'S-70 Okhotnik':     'S-70猎人',
}


# ============================================================
# Merged dictionary for convenient import
# ============================================================

ALL = {}
for d in [
    air_to_air, surface_to_air, anti_ship, land_attack_cruise,
    ballistic, anti_tank, anti_radiation, air_to_surface, manpads,
    aircraft, russian_srbm_irbm, russian_sam, russian_atgm,
    russian_naval, russian_asm, russian_misc, russian_uav,
]:
    ALL.update(d)
