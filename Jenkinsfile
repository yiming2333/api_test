pipeline {
    agent any

    options {
        timeout(time: 30, unit: 'MINUTES')
        disableConcurrentBuilds()
        buildDiscarder(logRotator(numToKeepStr: '30'))
    }

    parameters {
        choice(name: 'ENV', choices: ['dev', 'prod'], description: '选择运行环境')
        choice(name: 'MARK', choices: ['all', 'smoke', 'regression'], description: '选择用例标记')
    }

    environment {
        // ========== 系统路径 ==========
        PYTHON_PATH = 'C:/Users/27088/AppData/Local/Programs/Python/Python310/python.exe'

        // ========== pip 依赖源 ==========
        PIP_INDEX_URL = 'https://pypi.tuna.tsinghua.edu.cn/simple'

        // ========== Allure 报告相关 ==========
        ALLURE_RESULTS = 'reports/allure-results'
        ALLURE_REPORT_DIR = 'reports/allure-report'
        ALLURE_REPORT_NAME = 'AllureReport'

        // ========== 邮件配置 ==========
        MAIL_RECIPIENT = 'yiming_2333@sina.com'

        // ========== 编码设置 ==========
        PYTHONIOENCODING = 'utf-8'

        // ========== Git 配置 ==========
        GIT_URL = 'https://github.com/yiming2333/api_test.git'
        GIT_BRANCH = 'master'
        GIT_CREDENTIALS_ID = ''

        // ========== 报告链接 ==========
        REPORT_LINK = "${env.JENKINS_URL}job/${env.JOB_NAME}/${env.BUILD_NUMBER}/${env.ALLURE_REPORT_NAME}/"
    }

    stages {
        stage('0. 获取构建用户') {
            steps {
                script {
                    try {
                        wrap([$class: 'BuildUser']) {
                            env.TRIGGER_USER = env.BUILD_USER_ID ?: '未知(插件未生效)'
                        }
                    } catch (e) {
                        echo "⚠️ 无法获取构建用户: ${e.message}"
                        env.TRIGGER_USER = '未知'
                    }
                    echo "本次构建触发人: ${env.TRIGGER_USER}"
                }
            }
        }

        stage('1. 拉取代码') {
            options { retry(60) }
            steps {
                echo "正在从 Git 拉取代码..."
                script {
                    def gitConfig = [branch: env.GIT_BRANCH, url: env.GIT_URL]
                    if (env.GIT_CREDENTIALS_ID?.trim()) {
                        gitConfig.credentialsId = env.GIT_CREDENTIALS_ID
                    }
                    git gitConfig
                }
            }
        }

        stage('2. 安装依赖') {
            steps {
                echo "正在安装 Python 依赖..."
                bat """
                    chcp 65001
                    "${PYTHON_PATH}" -m pip install -r requirements.txt -q -i ${PIP_INDEX_URL}
                """
            }
        }

        stage('3. 执行测试') {
            steps {
                echo "开始执行 Pytest 测试..."
                script {
                    catchError(buildResult: 'FAILURE', stageResult: 'FAILURE') {
                        def markArg = params.MARK != 'all' ? "-m ${params.MARK}" : ""
                        bat """
                            chcp 65001
                            "${PYTHON_PATH}" -m pytest ${markArg} ^
                                --env=${params.ENV} ^
                                --alluredir=${ALLURE_RESULTS} ^
                                --clean-alluredir ^
                                -v
                        """
                    }
                }
            }
        }

        // ================================================================
        //  stage 3.5：写入 Allure Environment + Executor 元数据
        // ================================================================
        stage('3.5 写入 Allure 环境 & 执行器信息') {
            steps {
                script {
                    // ---------- 1. environment.properties ----------
                    def envProps = """
                        Environment=${params.ENV}
                        Python.Version=3.10
                        Pytest.Mark=${params.MARK}
                        Trigger.User=${env.TRIGGER_USER ?: 'unknown'}
                        Build.Number=${env.BUILD_NUMBER}
                        Git.Branch=${env.GIT_BRANCH}
                        Base.URL=${getBaseUrl(params.ENV)}
                        OS=Windows
                    """.stripIndent().trim()
                    writeFile file: "${ALLURE_RESULTS}/environment.properties", text: envProps, encoding: 'UTF-8'
                    echo "✅ environment.properties 已写入"

                    // ---------- 2. executor.json（手动写入，保证显示构建信息）----------
                    def reportUrl = "${env.JENKINS_URL}job/${env.JOB_NAME}/${env.BUILD_NUMBER}/${ALLURE_REPORT_NAME}/"
                    def buildUrl  = "${env.JENKINS_URL}job/${env.JOB_NAME}/${env.BUILD_NUMBER}/"
                    def jsonStr   = """{
                        "name": "Jenkins",
                        "type": "jenkins",
                        "url": "${env.JENKINS_URL}",
                        "buildOrder": ${env.BUILD_NUMBER},
                        "buildName": "#${env.BUILD_NUMBER}",
                        "buildUrl": "${buildUrl}",
                        "reportUrl": "${reportUrl}",
                        "reportName": "${ALLURE_REPORT_NAME}"
                    }"""
                    writeFile file: "${ALLURE_RESULTS}/executor.json", text: jsonStr, encoding: 'UTF-8'
                    echo "✅ executor.json 已写入"
                }
            }
        }

        // ================================================================
        //  stage 4：使用 Allure Jenkins Plugin 自动生成报告 + 处理趋势
        // ================================================================
        stage('4. 生成并发布 Allure 报告') {
            steps {
                script {
                    // 使用 allure 步骤，插件会自动：
                    // 1. 从历史构建中读取 history 数据（趋势图）
                    // 2. 生成新的 Allure 报告到默认目录（工作空间/allure-report）
                    // 3. 将新报告的历史数据归档，供后续构建使用
                    allure([
                        includeProperties: false,        // 不包含额外属性
                        jdk: '',                         // 使用默认JDK
                        properties: [],                  // 可选的额外属性
                        reportBuildPolicy: 'ALWAYS',     // 每次构建都生成报告
                        results: [[path: env.ALLURE_RESULTS]]  // 指定结果目录
                    ])
                    // 注意：插件生成的报告默认在 ${WORKSPACE}/allure-report，
                    // 但我们可以通过 report 参数指定，这里不指定，保持与插件默认一致。
                    // 为了后续 publishHTML 能找到，我们将默认报告复制到自定义目录（可选）
                    // 或者直接使用默认目录。为了方便，我们保持环境变量 ALLURE_REPORT_DIR 指向默认位置。
                    // 但插件默认输出目录是 'allure-report'，与我们的变量一致，所以无需额外操作。
                }

                // 使用 publishHTML 发布报告到 Jenkins 页面（可选，插件已经提供了 Allure 链接）
                // 但为了在构建页面显示 HTML 报告，可以保留
                publishHTML([
                    reportDir: env.ALLURE_REPORT_DIR,
                    reportFiles: 'index.html',
                    reportName: env.ALLURE_REPORT_NAME,
                    allowMissing: true,
                    keepAll: true,
                    alwaysLinkToLastBuild: false
                ])
            }
        }
    }

    post {
        always {
            echo "流水线执行结束"
            archiveArtifacts artifacts: 'logs/*.log', allowEmptyArchive: true
        }

        success {
            echo "✅ 恭喜！所有测试用例通过！"
            script { sendEmailNotification('SUCCESS', 'green', '✅') }
        }

        failure {
            echo "❌ 存在失败的测试用例，请查看 Allure 报告。"
            script { sendEmailNotification('FAILURE', 'red', '❌') }
        }
    }
}

// ========== 根据环境参数返回 base_url ==========
def getBaseUrl(String envName) {
    def urls = [
        'dev' : 'http://127.0.0.1:5000',
        'prod': 'https://api.example.com'
    ]
    return urls[envName] ?: 'unknown'
}

// ========== 邮件发送函数 ==========
def sendEmailNotification(String status, String color, String icon) {
    emailext (
        to: env.MAIL_RECIPIENT,
        subject: "${icon} 测试${status == 'SUCCESS' ? '通过' : '失败'} - ${env.JOB_NAME} - Build #${env.BUILD_NUMBER}",
        body: """
            <p>各位同事，大家好！</p>
            <p>项目 <strong>${env.JOB_NAME}</strong> 构建${status == 'SUCCESS' ? '成功' : '失败'}！</p>
            <ul>
                <li>构建编号：<strong>#${env.BUILD_NUMBER}</strong></li>
                <li>构建状态：<span style="color: ${color};">${icon} ${status}</span></li>
                <li>触发人：${env.TRIGGER_USER ?: '未知'}</li>
                <li>测试报告：<a href="${env.REPORT_LINK}">${env.REPORT_LINK}</a></li>
            </ul>
            <p>请点击上方链接查看 Allure 测试报告详情。</p>
            <hr/>
            <p style="font-size: 12px; color: gray;">此邮件由 Jenkins 自动发送，请勿回复。</p>
        """,
        mimeType: 'text/html'
    )
}