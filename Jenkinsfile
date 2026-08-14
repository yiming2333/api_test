pipeline {
    agent any

    parameters {
        choice(name: 'ENV', choices: ['dev', 'prod'], description: '选择运行环境')
        choice(name: 'MARK', choices: ['all', 'smoke', 'regression'], description: '选择用例标记')
    }

    environment {
        PYTHON_PATH = 'C:/Users/27088/AppData/Local/Programs/Python/Python310/python.exe'
        ALLURE_RESULTS = 'reports/allure-results'
        ALLURE_REPORT   = 'reports/allure-report'
        PYTHONIOENCODING = 'utf-8'   // 解决 Windows 控制台编码问题
    }

    stages {
        stage('1. 拉取代码') {
            options { retry(3) }
            steps {
                echo "正在从 Git 拉取代码..."
                git branch: 'master', url: 'https://github.com/yiming2333/api_test.git'
            }
        }

        stage('2. 安装依赖') {
            steps {
                echo "正在安装 Python 依赖..."
                bat """
                    chcp 65001
                    ${PYTHON_PATH} -m pip install -r requirements.txt -q -i https://pypi.tuna.tsinghua.edu.cn/simple
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
                            ${PYTHON_PATH} -m pytest ${markArg} ^
                                --env=${params.ENV} ^
                                --alluredir=${ALLURE_RESULTS} ^
                                --clean-alluredir ^
                                -v
                        """
                    }
                }
            }
        }

        stage('4. 生成并发布 Allure 报告') {
            steps {
                echo "正在生成 Allure 测试报告..."
                // 使用 Allure 插件，只需要指定结果目录路径
//                 allure 'reports/allure-results'
                step([
            $class: 'AllureReportBuilder',
            results: [[path: 'reports/allure-results']]
        ])
//                 // 使用命令行生成报告（确保 allure 命令在 PATH 中）
//                 bat """
//                     allure generate ${ALLURE_RESULTS} -o ${ALLURE_REPORT} --clean
//                 """
//                 // 通过 HTML Publisher 发布报告
//                 publishHTML([
//                     reportDir: 'reports/allure-report',
//                     reportFiles: 'index.html',
//                     reportName: 'Allure 测试报告',
//                     allowMissing: true,
//                     keepAll: false,
//                     alwaysLinkToLastBuild: false
//                 ])
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
        }
        failure {
            echo "❌ 存在失败的测试用例，请查看 Allure 报告。"
        }
    }
}